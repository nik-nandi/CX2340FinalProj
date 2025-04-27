from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import User, TripArea, TripLocation, ItineraryItem, Tour, TourInquiry, TripAlert, GuideReview, Bookmark
from django.contrib.auth import login
from django.contrib.auth.forms import AuthenticationForm
from django import forms
from django.http import JsonResponse, StreamingHttpResponse, HttpResponseForbidden, HttpResponseBadRequest
import requests
import json
from django.db.models import Count, Avg, Q
from django.conf import settings  # Import settings to access API key
from google import genai
from google.genai import types
import base64
import io
import re
from django.contrib.auth.forms import PasswordChangeForm
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.db import transaction, IntegrityError

def landing_page(request):
    return render(request, 'pages/landing.html')

class SignUpForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'role']

# Add a form for admins to edit users
class AdminEditUserForm(forms.ModelForm):
    # Allow password to be optional. Use PasswordInput for masking.
    password = forms.CharField(widget=forms.PasswordInput, required=False, help_text="Leave blank to keep the current password.")
    confirm_password = forms.CharField(widget=forms.PasswordInput, required=False, help_text="Confirm the new password.")

    class Meta:
        model = User
        fields = ['username', 'email', 'role', 'is_staff', 'is_superuser', 'password'] # Add password field

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        # Check if passwords match only if a new password is provided
        if password and password != confirm_password:
            raise forms.ValidationError("Passwords do not match.")
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get("password")
        if password: # Only set password if a new one was entered
            user.set_password(password)
        if commit:
            user.save()
        return user

def signup_view(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password'])  # Hash the password
            
            # If the user is registering as an admin, make them a superuser
            if form.cleaned_data['role'] == 'admin':
                user.is_staff = True
                user.is_superuser = True
            
            user.save()
            login(request, user)
            return redirect('profile') 
    else:
        form = SignUpForm()
    return render(request, 'pages/registration/signup.html', {'form': form})

@login_required
def profile_view(request):
    """Display the user profile page."""
    trip_areas = TripArea.objects.filter(user=request.user)
    context = {'trip_areas': trip_areas}

    if request.user.is_admin():
        user_count = User.objects.count()
        traveler_count = User.objects.filter(role='traveler').count()
        guide_count = User.objects.filter(role='guide').count()
        admin_count = User.objects.filter(role='admin').count()

        trip_area_count = TripArea.objects.count()
        avg_radius = TripArea.objects.aggregate(Avg('radius'))['radius__avg'] or 0

        itinerary_count = ItineraryItem.objects.count()
        trip_areas_with_items = TripArea.objects.annotate(item_count=Count('itinerary_items')).filter(item_count__gt=0)
        avg_items_per_trip = trip_areas_with_items.aggregate(Avg('item_count'))['item_count__avg'] or 0

        recent_trip_areas = TripArea.objects.select_related('user').prefetch_related('itinerary_items').order_by('-created_at')[:10]

        # Fetch ALL users for the admin management table, not just recent ones
        all_users = User.objects.order_by('username') # Changed from recent_users

        popular_destinations = (
            ItineraryItem.objects
            .values('place_id', 'name', 'address')
            .annotate(count=Count('place_id'))
            .order_by('-count')[:6]
        )

        context.update({
            'user_count': user_count,
            'traveler_count': traveler_count,
            'guide_count': guide_count,
            'admin_count': admin_count,
            'trip_area_count': trip_area_count,
            'avg_radius': avg_radius,
            'itinerary_count': itinerary_count,
            'avg_items_per_trip': avg_items_per_trip,
            'recent_trip_areas': recent_trip_areas,
            'all_users': all_users, # Changed context variable name
            'popular_destinations': popular_destinations,
        })

    recent_bookmarks = None
    if request.user.is_traveler:
        # Fetch recent bookmarks for travelers
        recent_bookmarks = Bookmark.objects.filter(user=request.user).order_by('-created_at')[:5] # Get latest 5

    context.update({
        'recent_bookmarks': recent_bookmarks, # Add recent bookmarks to context
    })

    return render(request, 'pages/profile.html', context)

@login_required
def map_ui(request):
    api_key = settings.GOOGLE_MAPS_API_KEY  # Get API key from settings
    trip_areas = TripArea.objects.filter(user=request.user)
    
    if request.method == 'POST':
        # Handle form submission to create new trip area
        if 'create_trip_area' in request.POST:
            name = request.POST.get('name')
            description = request.POST.get('description')
            latitude = float(request.POST.get('latitude'))
            longitude = float(request.POST.get('longitude'))
            radius = float(request.POST.get('radius'))
            
            trip_area = TripArea.objects.create(
                user=request.user,
                name=name,
                description=description,
                latitude=latitude,
                longitude=longitude,
                radius=radius
            )
            return redirect('map_ui')
    
    return render(request, 'pages/map_ui.html', {
        'api_key': api_key,
        'trip_areas': trip_areas
    })

@login_required
def itineraries_view(request):
    api_key = settings.GOOGLE_MAPS_API_KEY  # Get API key from settings
    
    # Get the selected trip area or the first one
    trip_area_id = request.GET.get('trip_area')
    user_trip_areas = TripArea.objects.filter(user=request.user)
    
    if trip_area_id:
        selected_trip_area = get_object_or_404(TripArea, id=trip_area_id, user=request.user)
    elif user_trip_areas.exists():
        selected_trip_area = user_trip_areas.first()
    else:
        selected_trip_area = None
    
    # Get any existing itinerary items for this trip area
    itinerary_items = []
    if selected_trip_area:
        itinerary_items = ItineraryItem.objects.filter(trip_area=selected_trip_area)
    
    context = {
        'api_key': api_key,
        'trip_areas': user_trip_areas,
        'selected_trip_area': selected_trip_area,
        'itinerary_items': itinerary_items,
    }
    
    return render(request, 'pages/itineraries.html', context)

@login_required
def search_attractions(request):
    """API endpoint to search for attractions near a trip area"""
    trip_area_id = request.GET.get('trip_area_id')
    attraction_type = request.GET.get('type', 'tourist_attraction')  # Default to tourist attractions
    
    try:
        trip_area = TripArea.objects.get(id=trip_area_id, user=request.user)
    except TripArea.DoesNotExist:
        return JsonResponse({'error': 'Trip area not found'}, status=404)
    
    api_key = settings.GOOGLE_MAPS_API_KEY  # Get API key from settings
    
    # Call Google Places API
    url = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        'location': f"{trip_area.latitude},{trip_area.longitude}",
        'radius': min(trip_area.radius * 1000, 50000),  # Convert km to meters, max 50km
        'type': attraction_type,
        'key': api_key
    }
    
    try:
        response = requests.get(url, params=params)
        data = response.json()
        
        if data.get('status') == 'OK':
            return JsonResponse({'results': data.get('results', [])})
        else:
            return JsonResponse({'error': data.get('status')}, status=400)
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def add_to_itinerary(request):
    """Add an attraction to the itinerary"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            trip_area_id = data.get('trip_area_id')
            place_data = data.get('place')
            
            # Validate trip area
            trip_area = get_object_or_404(TripArea, id=trip_area_id, user=request.user)
            
            # Check if this place is already in the itinerary
            existing_item = ItineraryItem.objects.filter(
                trip_area=trip_area,
                place_id=place_data.get('place_id')
            ).first()
            
            if existing_item:
                return JsonResponse({'status': 'already_exists', 'item_id': existing_item.id})
            
            # Create new itinerary item
            item = ItineraryItem.objects.create(
                trip_area=trip_area,
                place_id=place_data.get('place_id'),
                name=place_data.get('name'),
                address=place_data.get('vicinity', ''),
                types=','.join(place_data.get('types', [])),
                latitude=place_data.get('geometry', {}).get('location', {}).get('lat'),
                longitude=place_data.get('geometry', {}).get('location', {}).get('lng'),
                photo_reference=place_data.get('photos', [{}])[0].get('photo_reference', '') if place_data.get('photos') else '',
                order=ItineraryItem.objects.filter(trip_area=trip_area).count() + 1
            )
            
            return JsonResponse({'status': 'success', 'item_id': item.id})
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
def remove_from_itinerary(request, item_id):
    """Remove an attraction from the itinerary"""
    item = get_object_or_404(ItineraryItem, id=item_id, trip_area__user=request.user)
    trip_area = item.trip_area
    item.delete()
    
    # Reorder remaining items
    for i, remaining_item in enumerate(ItineraryItem.objects.filter(trip_area=trip_area).order_by('order')):
        remaining_item.order = i + 1
        remaining_item.save()
    
    return JsonResponse({'status': 'success'})

@login_required
def reorder_itinerary(request):
    """Reorder items in the itinerary"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            item_order = data.get('item_order', [])
            
            for index, item_id in enumerate(item_order):
                item = get_object_or_404(ItineraryItem, id=item_id, trip_area__user=request.user)
                item.order = index + 1
                item.save()
            
            return JsonResponse({'status': 'success'})
        
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
def translator(request):
    """Display the translator page."""
    context = {
        'languages': [
            {'code': 'en', 'name': 'English'},
            {'code': 'es', 'name': 'Spanish'},
            {'code': 'fr', 'name': 'French'},
            {'code': 'de', 'name': 'German'},
            {'code': 'it', 'name': 'Italian'},
            {'code': 'ja', 'name': 'Japanese'},
            {'code': 'ko', 'name': 'Korean'},
            {'code': 'zh', 'name': 'Chinese'},
            {'code': 'ru', 'name': 'Russian'},
            {'code': 'ar', 'name': 'Arabic'},
            {'code': 'hi', 'name': 'Hindi'},
            {'code': 'pt', 'name': 'Portuguese'},
            {'code': 'vi', 'name': 'Vietnamese'},
            {'code': 'th', 'name': 'Thai'},
        ]
    }
    return render(request, 'pages/translator.html', context)

@login_required
def translate_text(request):
    """API endpoint to translate text using Gemini."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST request required'}, status=400)
    
    try:
        data = json.loads(request.body)
        text = data.get('text', '')
        source_lang = data.get('source_lang', 'auto')
        target_lang = data.get('target_lang', 'en')
        
        if not text:
            return JsonResponse({'error': 'Text is required'}, status=400)
        
        # Initialize Gemini client
        client = genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options=types.HttpOptions(api_version='v1alpha')
        )
        
        model = "gemini-2.0-flash"
        
        # Build prompt for translation
        system_prompt = f"""You are a highly accurate translator. 
        Translate the following text from {source_lang if source_lang != 'auto' else 'the detected language'} to {target_lang}.
        Only provide the translation without additional comments or explanations.
        If the source language is 'auto', first detect the language and then translate.
        """
        
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=text)],
            ),
        ]
        
        generate_content_config = types.GenerateContentConfig(
            response_mime_type="text/plain",
            system_instruction=[
                types.Part.from_text(text=system_prompt),
            ],
        )
        
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=generate_content_config,
        )
        
        return JsonResponse({
            'translation': response.text,
            'detected_language': detect_language(text),
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def detect_language(text):
    """Helper function to detect the language of a text using Gemini."""
    try:
        if not text:
            return "Unknown"
            
        # Initialize Gemini client
        client = genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options=types.HttpOptions(api_version='v1alpha')
        )
        
        model = "gemini-2.0-flash"
        
        # Build prompt for language detection
        system_prompt = """Identify the language of the provided text.
        Respond with only the language name (e.g., "English", "Spanish", "French", etc.).
        Do not include any additional text or explanation."""
        
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=text)],
            ),
        ]
        
        generate_content_config = types.GenerateContentConfig(
            response_mime_type="text/plain",
            system_instruction=[
                types.Part.from_text(text=system_prompt),
            ],
        )
        
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=generate_content_config,
        )
        
        return response.text.strip()
        
    except Exception as e:
        print(f"Error detecting language: {e}")
        return "Unknown"

@login_required
def assistant(request):
    # Get user's trip areas
    trip_areas = TripArea.objects.filter(user=request.user)
    
    context = {
        'trip_areas': trip_areas,
        'selected_trip_area': None,
    }
    return render(request, 'pages/assistant.html', context)

@login_required
def ask_assistant(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST request required'}, status=400)
    
    try:
        data = json.loads(request.body)
        user_message = data.get('message', '')
        trip_area_id = data.get('trip_area_id')
        
        # Get trip context if trip_area_id is provided
        trip_context = ""
        if trip_area_id:
            try:
                trip_area = TripArea.objects.get(id=trip_area_id, user=request.user)
                trip_context = f"Trip Area: {trip_area.name}\nDescription: {trip_area.description}\nLocation: Lat {trip_area.latitude}, Lng {trip_area.longitude}\n"
                
                # Add itinerary items if any
                itinerary_items = ItineraryItem.objects.filter(trip_area=trip_area).order_by('order')
                if itinerary_items:
                    trip_context += "\nItinerary:\n"
                    for i, item in enumerate(itinerary_items):
                        trip_context += f"{i+1}. {item.name} - {item.address}\n"
            except TripArea.DoesNotExist:
                pass
        
        def stream_response():
            # Initialize Gemini client
            client = genai.Client(
                api_key=settings.GEMINI_API_KEY,
                http_options=types.HttpOptions(api_version='v1alpha')
            )

            model = "gemini-2.0-flash"
            
            # Create system prompt with context
            system_prompt = """You are a helpful AI travel assistant. Provide concise, accurate travel advice and recommendations.
            Be friendly but professional. If asked about specific details for places the user hasn't mentioned, suggest options
            that would typically be good for travelers. For restaurant recommendations, suggest local cuisine options when possible."""
            
            # Add trip context if available
            if trip_context:
                system_prompt += f"\n\nThe user is planning a trip with the following details:\n{trip_context}"
            
            contents = [
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=user_message)],
                ),
            ]
            
            generate_content_config = types.GenerateContentConfig(
                response_mime_type="text/plain",
                system_instruction=[
                    types.Part.from_text(text=system_prompt),
                ],
            )
            
            # Stream the response
            for chunk in client.models.generate_content_stream(
                model=model,
                contents=contents,
                config=generate_content_config,
            ):
                if chunk.text:
                    yield f"data: {json.dumps({'text': chunk.text})}\n\n"
            
            yield "data: [DONE]\n\n"
            
        return StreamingHttpResponse(stream_response(), content_type="text/event-stream")
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

# Tour Guide features
@login_required
def create_tour_view(request):
    """Display form for creating a new tour"""
    if not request.user.is_guide():
        messages.error(request, "Only tour guides can create tours.")
        return redirect('profile')
        
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description')
        duration = request.POST.get('duration')
        price = request.POST.get('price')
        max_travelers = request.POST.get('max_travelers')
        location = request.POST.get('location')
        
        # Create new tour
        tour = Tour.objects.create(
            guide=request.user,
            name=name,
            description=description,
            duration=duration,
            price=price,
            max_travelers=max_travelers,
            location=location
        )
        
        messages.success(request, "Tour created successfully!")
        return redirect('my_tours')
    
    return render(request, 'pages/create_tour.html')

@login_required
def my_tours_view(request):
    """Display all tours created by the guide"""
    if not request.user.is_guide():
        messages.error(request, "Only tour guides can access this page.")
        return redirect('profile')
        
    tours = Tour.objects.filter(guide=request.user).order_by('-created_at')
    
    return render(request, 'pages/my_tours.html', {
        'tours': tours
    })

@login_required
def edit_tour_view(request, tour_id):
    """Edit an existing tour"""
    if not request.user.is_guide():
        messages.error(request, "Only tour guides can edit tours.")
        return redirect('profile')
    
    tour = get_object_or_404(Tour, id=tour_id, guide=request.user)
    
    if request.method == 'POST':
        tour.name = request.POST.get('name')
        tour.description = request.POST.get('description')
        tour.duration = request.POST.get('duration')
        tour.price = request.POST.get('price')
        tour.max_travelers = request.POST.get('max_travelers')
        tour.location = request.POST.get('location')
        tour.save()
        
        messages.success(request, "Tour updated successfully!")
        return redirect('my_tours')
    
    return render(request, 'pages/edit_tour.html', {
        'tour': tour
    })

# Tour assignment for travelers
@login_required
def browse_guides_view(request):
    """Browse available tour guides and tours"""
    if not request.user.is_traveler():
        messages.error(request, "This feature is only for travelers.")
        return redirect('profile')
    
    trip_area_id = request.GET.get('trip_area')
    selected_trip_area = None
    
    if trip_area_id:
        selected_trip_area = get_object_or_404(TripArea, id=trip_area_id, user=request.user)
    
    # Get available guides with average ratings and review counts
    guides_with_ratings = User.objects.filter(role='guide').annotate(
        avg_rating=Avg('reviews_received__rating'),
        review_count=Count('reviews_received__id') # Use reviews_received__id for accurate count
    )
    
    # Get tours and annotate their guides with ratings
    tours = Tour.objects.filter(guide__role='guide').select_related('guide').annotate(
        guide_avg_rating=Avg('guide__reviews_received__rating'),
        guide_review_count=Count('guide__reviews_received__id') # Use reviews_received__id
    )
    
    # If trip area is selected, get the assigned guide with annotations
    assigned_guide_annotated = None
    if selected_trip_area and selected_trip_area.assigned_guide:
        try:
            # Find the assigned guide within the annotated queryset
            assigned_guide_annotated = guides_with_ratings.get(id=selected_trip_area.assigned_guide.id)
        except User.DoesNotExist:
            # Fallback if guide not found in annotated list (shouldn't normally happen)
            assigned_guide_annotated = selected_trip_area.assigned_guide
            # Manually add default annotation attributes if needed
            assigned_guide_annotated.avg_rating = 0
            assigned_guide_annotated.review_count = 0
            
    # Get user's trip areas for the dropdown
    trip_areas = TripArea.objects.filter(user=request.user)
    
    return render(request, 'pages/browse_guides.html', {
        'guides': guides_with_ratings, # Keep for potential separate guide listing
        'tours': tours,
        'trip_areas': trip_areas,
        'selected_trip_area': selected_trip_area,
        'assigned_guide': assigned_guide_annotated # Pass the annotated guide object
    })

@login_required
def guide_profile_view(request, guide_id):
    """View a specific guide's profile and reviews"""
    if not request.user.is_traveler():
        messages.error(request, "This feature is only for travelers.")
        return redirect('profile')
    
    guide = get_object_or_404(User, id=guide_id, role='guide')
    tours = Tour.objects.filter(guide=guide)
    reviews = GuideReview.objects.filter(guide=guide)
    avg_rating = reviews.aggregate(Avg('rating'))['rating__avg'] or 0
    
    # Get the user's trip areas to allow them to select one for review
    trip_areas = TripArea.objects.filter(
        user=request.user, 
        assigned_guide=guide
    )
    
    # Check if the user has already reviewed this guide
    user_reviews = GuideReview.objects.filter(
        traveler=request.user,
        guide=guide
    )
    
    has_reviewed = user_reviews.exists()
    user_can_review = trip_areas.exists() and not has_reviewed
    
    return render(request, 'pages/guide_profile.html', {
        'guide': guide,
        'tours': tours,
        'reviews': reviews,
        'avg_rating': avg_rating,
        'trip_areas': trip_areas,
        'user_can_review': user_can_review,
        'has_reviewed': has_reviewed,
        'user_review': user_reviews.first() if has_reviewed else None
    })

@login_required
def submit_review_view(request, guide_id):
    """Submit a review for a guide"""
    if not request.user.is_traveler():
        messages.error(request, "Only travelers can submit reviews.")
        return redirect('profile')
    
    guide = get_object_or_404(User, id=guide_id, role='guide')
    
    # Check if user has a trip with this guide assigned
    user_trips_with_guide = TripArea.objects.filter(
        user=request.user, 
        assigned_guide=guide
    )
    
    if not user_trips_with_guide.exists():
        messages.error(request, "You can only review guides that have been assigned to your trips.")
        return redirect('guide_profile', guide_id=guide_id)
    
    # Check if user has already reviewed this guide
    existing_review = GuideReview.objects.filter(
        traveler=request.user,
        guide=guide
    ).first()
    
    if request.method == 'POST':
        trip_area_id = request.POST.get('trip_area')
        rating = request.POST.get('rating')
        comment = request.POST.get('comment')
        
        if not all([trip_area_id, rating, comment]):
            messages.error(request, "All fields are required.")
            return redirect('submit_review', guide_id=guide_id)
        
        trip_area = get_object_or_404(TripArea, id=trip_area_id, user=request.user)
        
        # Update existing review or create new one
        if existing_review:
            existing_review.rating = rating
            existing_review.comment = comment
            existing_review.trip_area = trip_area
            existing_review.save()
            messages.success(request, "Your review has been updated.")
        else:
            GuideReview.objects.create(
                traveler=request.user,
                guide=guide,
                trip_area=trip_area,
                rating=rating,
                comment=comment
            )
            messages.success(request, "Your review has been submitted.")
        
        return redirect('guide_profile', guide_id=guide_id)
    
    return render(request, 'pages/submit_review.html', {
        'guide': guide,
        'trip_areas': user_trips_with_guide,
        'existing_review': existing_review
    })

@login_required
def my_reviews_view(request):
    """View all reviews submitted by the logged-in traveler"""
    if not request.user.is_traveler():
        messages.error(request, "This feature is only for travelers.")
        return redirect('profile')
    
    reviews = GuideReview.objects.filter(traveler=request.user)
    
    return render(request, 'pages/my_reviews.html', {
        'reviews': reviews
    })

@login_required
def guide_reviews_view(request):
    """View for guides to see reviews about them"""
    if not request.user.is_guide():
        messages.error(request, "This feature is only for tour guides.")
        return redirect('profile')
    
    reviews = GuideReview.objects.filter(guide=request.user)
    avg_rating = reviews.aggregate(Avg('rating'))['rating__avg'] or 0
    
    return render(request, 'pages/guide_reviews.html', {
        'reviews': reviews,
        'avg_rating': avg_rating
    })

@login_required
def assign_guide_view(request):
    """Assign a guide to a trip area"""
    if request.method != 'POST':
        return redirect('browse_guides')
    
    trip_area_id = request.POST.get('trip_area_id')
    guide_id = request.POST.get('guide_id')
    
    trip_area = get_object_or_404(TripArea, id=trip_area_id, user=request.user)
    guide = get_object_or_404(User, id=guide_id, role='guide')
    
    # Assign guide to trip area
    trip_area.assigned_guide = guide
    trip_area.save()
    
    messages.success(request, f"{guide.username} has been assigned as your tour guide!")
    return redirect('profile')

@login_required
def remove_guide_view(request, trip_area_id):
    """Remove an assigned guide from a trip area"""
    trip_area = get_object_or_404(TripArea, id=trip_area_id, user=request.user)
    
    if trip_area.assigned_guide:
        guide_name = trip_area.assigned_guide.username
        trip_area.assigned_guide = None
        trip_area.save()
        messages.success(request, f"{guide_name} has been removed as your tour guide.")
    
    # Check if there's a next parameter to determine where to redirect
    next_url = request.POST.get('next', request.GET.get('next', 'browse_guides'))
    return redirect(next_url)

@login_required
def send_inquiry_view(request, trip_area_id=None):
    """View for travelers to send inquiries to their assigned guide"""
    trip_area = None
    
    # If trip_area_id is provided, get that specific trip area
    if trip_area_id:
        trip_area = get_object_or_404(TripArea, id=trip_area_id, user=request.user)
        if not trip_area.assigned_guide:
            messages.error(request, "This trip area doesn't have an assigned guide.")
            return redirect('profile')
    
    # Get all trip areas with assigned guides for dropdown
    trip_areas_with_guides = TripArea.objects.filter(
        user=request.user,
        assigned_guide__isnull=False
    )
    
    if request.method == 'POST':
        selected_trip_area_id = request.POST.get('trip_area')
        subject = request.POST.get('subject')
        message = request.POST.get('message')
        
        if not selected_trip_area_id:
            messages.error(request, "Please select a trip area.")
            return render(request, 'pages/send_inquiry.html', {
                'trip_areas': trip_areas_with_guides,
                'selected_trip_area': trip_area
            })
        
        selected_trip_area = get_object_or_404(TripArea, id=selected_trip_area_id, user=request.user)
        
        if not selected_trip_area.assigned_guide:
            messages.error(request, "The selected trip area doesn't have an assigned guide.")
            return redirect('send_inquiry')
        
        # Create the inquiry
        inquiry = TourInquiry.objects.create(
            traveler=request.user,
            guide=selected_trip_area.assigned_guide,
            trip_area=selected_trip_area,
            subject=subject,
            message=message
        )
        
        messages.success(request, "Your inquiry has been sent to the guide.")
        return redirect('my_inquiries')
    
    return render(request, 'pages/send_inquiry.html', {
        'trip_areas': trip_areas_with_guides,
        'selected_trip_area': trip_area
    })

@login_required
def my_inquiries_view(request):
    """View for travelers to see their sent inquiries"""
    if not request.user.is_traveler():
        messages.error(request, "This feature is only for travelers.")
        return redirect('profile')
        
    inquiries = TourInquiry.objects.filter(traveler=request.user)
    
    return render(request, 'pages/my_inquiries.html', {
        'inquiries': inquiries
    })

@login_required
def guide_inbox_view(request):
    """View for guides to see their received inquiries"""
    if not request.user.is_guide():
        messages.error(request, "This feature is only for tour guides.")
        return redirect('profile')
    
    # Get filter parameter from GET request
    status_filter = request.GET.get('status', 'all')
    
    # Filter inquiries based on status
    if status_filter == 'new':
        inquiries = TourInquiry.objects.filter(guide=request.user, status='new')
    elif status_filter == 'read':
        inquiries = TourInquiry.objects.filter(guide=request.user, status='read')
    elif status_filter == 'replied':
        inquiries = TourInquiry.objects.filter(guide=request.user, status='replied')
    elif status_filter == 'archived':
        inquiries = TourInquiry.objects.filter(guide=request.user, status='archived')
    else:
        inquiries = TourInquiry.objects.filter(guide=request.user)
    
    # Count of new inquiries for notification badge
    new_inquiries_count = TourInquiry.objects.filter(guide=request.user, status='new').count()
    
    return render(request, 'pages/guide_inbox.html', {
        'inquiries': inquiries,
        'status_filter': status_filter,
        'new_inquiries_count': new_inquiries_count
    })

@login_required
def inquiry_detail_view(request, inquiry_id):
    """View for reading and responding to an inquiry"""
    # Check if user is the guide or the traveler of this inquiry
    inquiry = get_object_or_404(
        TourInquiry, 
        Q(guide=request.user) | Q(traveler=request.user),
        id=inquiry_id
    )
    
    # If the guide is viewing this for the first time, mark as read
    if request.user == inquiry.guide and inquiry.status == 'new':
        inquiry.status = 'read'
        inquiry.save()
    
    if request.method == 'POST' and request.user == inquiry.guide:
        response = request.POST.get('response')
        inquiry.response = response
        inquiry.status = 'replied'
        inquiry.save()
        messages.success(request, "Response sent successfully!")
        return redirect('guide_inbox')
    
    return render(request, 'pages/inquiry_detail.html', {
        'inquiry': inquiry
    })

@login_required
def update_inquiry_status(request, inquiry_id):
    """AJAX view to update the status of an inquiry"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST request required'}, status=400)
    
    # Only the guide can update status
    inquiry = get_object_or_404(TourInquiry, id=inquiry_id, guide=request.user)
    
    try:
        data = json.loads(request.body)
        new_status = data.get('status')
        
        if new_status not in [status for status, _ in TourInquiry.STATUS_CHOICES]:
            return JsonResponse({'error': 'Invalid status'}, status=400)
        
        inquiry.status = new_status
        inquiry.save()
        
        return JsonResponse({'status': 'success'})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

# New view for Admin to edit user details
@login_required
def admin_edit_user(request, user_id):
    # Ensure only admins can access this view
    if not request.user.is_admin():
        messages.error(request, "You do not have permission to access this page.")
        return redirect('profile')

    user_to_edit = get_object_or_404(User, id=user_id)

    if request.method == 'POST':
        form = AdminEditUserForm(request.POST, instance=user_to_edit)
        if form.is_valid():
            # Prevent admin from accidentally removing their own admin rights
            if user_to_edit == request.user and not form.cleaned_data.get('is_superuser'):
                 messages.error(request, "You cannot remove your own admin privileges.")
            elif user_to_edit == request.user and form.cleaned_data.get('role') != 'admin':
                 messages.error(request, "You cannot change your own role from admin.")
            else:
                form.save()
                messages.success(request, f"User '{user_to_edit.username}' updated successfully.")
                return redirect('profile') # Redirect back to profile/admin dashboard
        else:
            # Add form errors to messages if save fails
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")

    else: # GET request
        form = AdminEditUserForm(instance=user_to_edit)
        # Don't pre-fill password fields on GET
        form.fields['password'].initial = ''
        form.fields['confirm_password'].initial = ''


    return render(request, 'pages/admin_edit_user.html', {
        'form': form,
        'user_to_edit': user_to_edit
    })

@login_required
def trip_alerts_view(request, trip_area_id):
    """View for travelers to see alerts for their trip area"""
    trip_area = get_object_or_404(TripArea, id=trip_area_id, user=request.user)
    alerts = TripAlert.objects.filter(trip_area=trip_area, is_active=True)
    
    context = {
        'trip_area': trip_area,
        'alerts': alerts,
        'api_key': settings.GOOGLE_MAPS_API_KEY  # Add API key to context
    }
    return render(request, 'pages/trip_alerts.html', context)

@login_required
def guide_alerts_view(request):
    """View for guides to manage their created alerts"""
    if not request.user.is_guide():
        messages.error(request, "Only tour guides can access this page.")
        return redirect('profile')
    
    # Get trip areas where this guide is assigned
    guided_areas = TripArea.objects.filter(assigned_guide=request.user)
    
    # Get alerts created by this guide
    alerts = TripAlert.objects.filter(creator=request.user)
    
    context = {
        'guided_areas': guided_areas,
        'alerts': alerts
    }
    return render(request, 'pages/guide_alerts.html', context)

@login_required
def create_alert_view(request):
    """View for guides to create a new alert"""
    if not request.user.is_guide():
        messages.error(request, "Only tour guides can create alerts.")
        return redirect('profile')
    
    # Get trip areas where this guide is assigned
    guided_areas = TripArea.objects.filter(assigned_guide=request.user)
    
    if request.method == 'POST':
        trip_area_id = request.POST.get('trip_area')
        title = request.POST.get('title')
        description = request.POST.get('description')
        latitude = request.POST.get('latitude')
        longitude = request.POST.get('longitude')
        event_date = request.POST.get('event_date')
        
        # Validate all required fields are present
        if not all([trip_area_id, title, description, latitude, longitude]):
            messages.error(request, "All required fields must be filled.")
            return render(request, 'pages/create_alert.html', {
                'guided_areas': guided_areas,
                'api_key': settings.GOOGLE_MAPS_API_KEY,
                'form_data': request.POST  # Return form data to repopulate
            })
        
        # Validate trip area belongs to areas where guide is assigned
        trip_area = get_object_or_404(TripArea, id=trip_area_id, assigned_guide=request.user)
        
        # Create new alert
        alert = TripAlert.objects.create(
            trip_area=trip_area,
            creator=request.user,
            title=title,
            description=description,
            latitude=float(latitude),  # Convert to float for safety
            longitude=float(longitude),  # Convert to float for safety
            event_date=event_date if event_date else None
        )
        
        messages.success(request, "Alert created successfully!")
        return redirect('guide_alerts')
    
    context = {
        'guided_areas': guided_areas,
        'api_key': settings.GOOGLE_MAPS_API_KEY,  # Ensure API key is properly set in settings
    }
    return render(request, 'pages/create_alert.html', context)

@login_required
def edit_alert_view(request, alert_id):
    """View for guides to edit an existing alert"""
    if not request.user.is_guide():
        messages.error(request, "Only tour guides can edit alerts.")
        return redirect('profile')
    
    alert = get_object_or_404(TripAlert, id=alert_id, creator=request.user)
    
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        latitude = request.POST.get('latitude')
        longitude = request.POST.get('longitude')
        event_date = request.POST.get('event_date')
        is_active = request.POST.get('is_active') == 'on'
        
        # Update alert
        alert.title = title
        alert.description = description
        alert.latitude = latitude
        alert.longitude = longitude
        alert.event_date = event_date if event_date else None
        alert.is_active = is_active
        alert.save()
        
        messages.success(request, "Alert updated successfully!")
        return redirect('guide_alerts')
    
    context = {
        'alert': alert,
        'api_key': settings.GOOGLE_MAPS_API_KEY
    }
    return render(request, 'pages/edit_alert.html', context)

@login_required
def delete_alert_view(request, alert_id):
    """View for guides to delete an alert"""
    if not request.user.is_guide():
        messages.error(request, "Only tour guides can delete alerts.")
        return redirect('profile')
    
    alert = get_object_or_404(TripAlert, id=alert_id, creator=request.user)
    
    if request.method == 'POST':
        alert.delete()
        messages.success(request, "Alert deleted successfully!")
        return redirect('guide_alerts')
    
    return render(request, 'pages/delete_alert.html', {'alert': alert})

# --- Bookmark Views ---

@login_required
def bookmarks_view(request):
    """Displays the user's bookmarked locations."""
    bookmarks = Bookmark.objects.filter(user=request.user).order_by('-created_at')
    context = {
        'bookmarks': bookmarks,
        'api_key': settings.GOOGLE_MAPS_API_KEY,
    }
    return render(request, 'pages/bookmarks.html', context)

@login_required
@require_POST
def add_bookmark(request):
    """Adds a location to the user's bookmarks via API."""
    try:
        data = json.loads(request.body)
        place = data.get('place')
        bookmark_type = data.get('type', 'other') # Get type, default to 'other'

        if not place or 'geometry' not in place or 'location' not in place['geometry']:
            return JsonResponse({'error': 'Invalid place data provided.'}, status=400)

        lat = place['geometry']['location']['lat']
        lng = place['geometry']['location']['lng']
        name = place.get('name', 'Unnamed Location')
        address = place.get('vicinity') or place.get('formatted_address') # Use vicinity or formatted_address
        place_id = place.get('place_id')

        # Use get_or_create to avoid duplicates based on user and location
        # Using lat/lng might be better if place_id isn't always present or unique enough across searches
        bookmark, created = Bookmark.objects.get_or_create(
            user=request.user,
            latitude=lat,
            longitude=lng,
            defaults={
                'name': name,
                'address': address,
                'place_id': place_id,
                'type': bookmark_type,
            }
        )

        if created:
            return JsonResponse({'status': 'success', 'bookmark_id': bookmark.id})
        else:
            # If it already exists, maybe update its details? Or just confirm it exists.
            # For now, let's just return success even if it existed.
            return JsonResponse({'status': 'success', 'bookmark_id': bookmark.id, 'message': 'Bookmark already exists.'})

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data.'}, status=400)
    except IntegrityError:
         # This might happen if unique_together constraint fails concurrently, though get_or_create handles most cases
         return JsonResponse({'error': 'Bookmark likely already exists (concurrent request).'}, status=409)
    except Exception as e:
        # Log the exception e
        print(f"Error adding bookmark: {e}")
        return JsonResponse({'error': 'An unexpected error occurred.'}, status=500)

@login_required
@require_POST
def remove_bookmark(request, bookmark_id):
    """Removes a bookmark via API."""
    try:
        bookmark = get_object_or_404(Bookmark, id=bookmark_id, user=request.user)
        bookmark.delete()
        return JsonResponse({'status': 'success'})
    except Bookmark.DoesNotExist:
         return JsonResponse({'error': 'Bookmark not found or you do not have permission.'}, status=404)
    except Exception as e:
        # Log the exception e
        print(f"Error removing bookmark: {e}")
        return JsonResponse({'error': 'An unexpected error occurred.'}, status=500)

@login_required
@require_POST
def update_bookmark_notes(request):
    """Updates the notes for a specific bookmark via API."""
    try:
        data = json.loads(request.body)
        bookmark_id = data.get('bookmark_id')
        notes = data.get('notes', '') # Default to empty string if notes are cleared

        if bookmark_id is None:
            return JsonResponse({'error': 'Bookmark ID is required.'}, status=400)

        bookmark = get_object_or_404(Bookmark, id=bookmark_id, user=request.user)
        bookmark.notes = notes
        bookmark.save()

        return JsonResponse({'status': 'success', 'notes': bookmark.notes})
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data.'}, status=400)
    except Bookmark.DoesNotExist:
         return JsonResponse({'error': 'Bookmark not found or you do not have permission.'}, status=404)
    except Exception as e:
        # Log the exception e
        print(f"Error updating bookmark notes: {e}")
        return JsonResponse({'error': 'An unexpected error occurred.'}, status=500)
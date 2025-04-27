from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login

from project.settings import GOOGLE_API_KEY
from .models import User, TripArea, TripLocation, ItineraryItem, LocalEvent
from django.contrib.auth.forms import AuthenticationForm
from django import forms
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
import requests
import json
from django.conf import settings
from django.db.models import Count, Avg
from django.contrib.contenttypes.models import ContentType
from django.contrib.admin.models import LogEntry, ADDITION # Import ADDITION

def handle_error(e):
    return JsonResponse({'error': str(e)}, status=500)
def landing_page(request):
    return render(request, 'pages/landing.html')

class SignUpForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'role']

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
            elif form.cleaned_data['role'] == 'Travel Guide':
                user.is_staff = True
                user.is_superuser = False
            user.save()
            login(request, user)  # Automatically log them in
            return redirect('landing')
    else:
        form = SignUpForm()
    return render(request, 'pages/registration/signup.html', {'form': form})

@login_required
def profile_view(request):
    """Display the user profile page."""
    trip_areas = TripArea.objects.filter(user=request.user)
    
    # Add admin dashboard data if user is an admin
    context = {'trip_areas': trip_areas}
    
    if request.user.is_admin():
        # Get statistics for admin dashboard
        user_count = User.objects.count()
        traveler_count = User.objects.filter(role='traveler').count()
        guide_count = User.objects.filter(role='guide').count()
        admin_count = User.objects.filter(role='admin').count()
        
        trip_area_count = TripArea.objects.count()
        avg_radius = TripArea.objects.aggregate(Avg('radius'))['radius__avg'] or 0
        
        itinerary_count = ItineraryItem.objects.count()
        # Calculate average items per trip area
        trip_areas_with_items = TripArea.objects.annotate(item_count=Count('itinerary_items')).filter(item_count__gt=0)
        avg_items_per_trip = trip_areas_with_items.aggregate(Avg('item_count'))['item_count__avg'] or 0
        
        # Get recent trip areas
        recent_trip_areas = TripArea.objects.select_related('user').prefetch_related('itinerary_items').order_by('-created_at')[:10]
        
        # Get recent users
        recent_users = User.objects.order_by('-date_joined')[:10]
        
        # Get popular destinations (places added to multiple itineraries)
        # Get recent log entries
        recent_logs = LogEntry.objects.select_related('user', 'content_type').order_by('-action_time')[:15]

        # Get all users for management section
        all_users = User.objects.order_by('username')

        # Get popular destinations (places added to multiple itineraries)
        popular_destinations = (
            ItineraryItem.objects
            .values('place_id', 'name', 'address')
            .annotate(count=Count('place_id'))
            .order_by('-count')[:6]
        )
        
        # Add all data to context
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
            'recent_users': recent_users,
            'popular_destinations': popular_destinations,
            'recent_logs': recent_logs,  # Add logs to context
            'all_users': all_users,      # Add all users to context
        })
    
    return render(request, 'pages/profile.html', context)

@login_required
def map_ui(request):
    api_key = GOOGLE_API_KEY
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
            
            # Log the creation action
            LogEntry.objects.log_action(
                user_id=request.user.pk,
                content_type_id=ContentType.objects.get_for_model(trip_area).pk,
                object_id=trip_area.pk,
                object_repr=str(trip_area),
                action_flag=ADDITION, # Use ADDITION for creation
                change_message="User created a new trip area."
            )
            
            return redirect('map_ui')
    
    return render(request, 'pages/map_ui.html', {
        'api_key': api_key,
        'trip_areas': trip_areas
    })

@login_required
def itineraries_view(request):
    api_key = GOOGLE_API_KEY
    
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
    
    api_key = GOOGLE_API_KEY
    
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
            
            # Log the addition action
            LogEntry.objects.log_action(
                user_id=request.user.pk,
                content_type_id=ContentType.objects.get_for_model(item).pk,
                object_id=item.pk,
                object_repr=str(item),
                action_flag=ADDITION, # Use ADDITION for creation/addition
                change_message=f"User added '{item.name}' to itinerary '{trip_area.name}'."
            )
            
            return JsonResponse({'status': 'success', 'item_id': item.id})
            
        except Exception as e:
            return handle_error(e)
    
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
            return handle_error(e)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

class LocalEventForm(forms.ModelForm):
    class Meta:
        model = LocalEvent
        fields = ['name', 'description', 'location', 'date']

@login_required
def local_events_list(request):
    events = LocalEvent.objects.order_by('date')
    return render(request, 'pages/local_events_list.html', {'events': events})

@login_required
def create_local_event(request):
    if not request.user.is_guide():  # Only staff users = Travel Guides
        return HttpResponseForbidden("You are not allowed to create events.")

    if request.method == 'POST':
        form = LocalEventForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('local_events_list')
    else:
        form = LocalEventForm()
    return render(request, 'pages/create_local_event.html', {'form': form})

@login_required
def update_local_event(request, event_id):
    event = get_object_or_404(LocalEvent, id=event_id)
    if not request.user.is_guide():
        return HttpResponseForbidden("You are not allowed to update events.")

    if request.method == 'POST':
        if 'save_changes' in request.POST:
            form = LocalEventForm(request.POST, instance=event)
            if form.is_valid():
                form.save()
                return redirect('local_events_list')
        elif 'delete_event' in request.POST:
            event.delete()
            return redirect('local_events_list')
    else:
        form = LocalEventForm(instance=event)

    return render(request, 'pages/update_local_event.html', {'form': form, 'event': event})

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login
from .models import User, TripArea, TripLocation, ItineraryItem
from django.contrib.auth.forms import AuthenticationForm
from django import forms
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
import requests
import json

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
    return render(request, 'pages/profile.html', {'trip_areas': trip_areas})

@login_required
def map_ui(request):
    api_key = 'AIzaSyCIGrBb--vJ9luPpJjnwUDfp92ER04umMI'
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
    api_key = 'AIzaSyCIGrBb--vJ9luPpJjnwUDfp92ER04umMI'
    
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
    
    api_key = 'AIzaSyCIGrBb--vJ9luPpJjnwUDfp92ER04umMI'
    
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
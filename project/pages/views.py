from django.shortcuts import render, redirect
from django.contrib.auth import login
from .models import User, TripArea, TripLocation
from django.contrib.auth.forms import AuthenticationForm
from django import forms
from django.contrib.auth.decorators import login_required

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
    api_key = 'AIzaSyClWa93Hx08igxCiwgj3oD64ia9DlYAfLM'  # Replace with your actual API key if needed
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

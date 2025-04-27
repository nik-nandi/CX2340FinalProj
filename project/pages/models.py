from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    ROLE_CHOICES = (
        ('traveler', 'Traveler'),
        ('guide', 'Tour Guide'),
        ('admin', 'Admin'),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='traveler')

    def is_traveler(self):
        return self.role == 'traveler'
    
    def is_guide(self):
        return self.role == 'guide'

    def is_admin(self):
        return self.role == 'admin'

class TripArea(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='trip_areas')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    radius = models.FloatField()  # in kilometers
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.name} - {self.user.username}"

class TripLocation(models.Model):
    trip_area = models.ForeignKey(TripArea, on_delete=models.CASCADE, related_name='locations')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    address = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.name} - {self.trip_area.name}"

class ItineraryItem(models.Model):
    trip_area = models.ForeignKey(TripArea, on_delete=models.CASCADE, related_name='itinerary_items')
    place_id = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255)
    photo_reference = models.CharField(max_length=500, null=True, blank=True)
    types = models.CharField(max_length=255, blank=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)
    order = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['order', 'created_at']
    
    def __str__(self):
        return f"{self.name} - {self.trip_area.name}"

class LocalEvent(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    location = models.CharField(max_length=255)
    date = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

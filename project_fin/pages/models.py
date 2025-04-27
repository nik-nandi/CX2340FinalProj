from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.conf import settings
from django.utils.translation import gettext_lazy as _

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
    assigned_guide = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='guided_trips'
    )
    
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

class Tour(models.Model):
    guide = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tours')
    name = models.CharField(max_length=100)
    description = models.TextField()
    duration = models.CharField(max_length=50)  # e.g. "2 hours", "Half day"
    price = models.DecimalField(max_digits=10, decimal_places=2)
    max_travelers = models.PositiveIntegerField(default=10)
    location = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name

class TourInquiry(models.Model):
    STATUS_CHOICES = (
        ('new', 'New'),
        ('read', 'Read'),
        ('replied', 'Replied'),
        ('archived', 'Archived'),
    )
    
    traveler = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_inquiries')
    guide = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_inquiries')
    trip_area = models.ForeignKey(TripArea, on_delete=models.CASCADE, related_name='inquiries', null=True, blank=True)
    subject = models.CharField(max_length=100)
    message = models.TextField()
    response = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Inquiry from {self.traveler.username} to {self.guide.username}"
    
    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = "Tour Inquiries"

class TripAlert(models.Model):
    trip_area = models.ForeignKey(TripArea, related_name='alerts', on_delete=models.CASCADE)
    creator = models.ForeignKey(User, related_name='created_alerts', on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField()
    latitude = models.FloatField()
    longitude = models.FloatField()
    event_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

class GuideReview(models.Model):
    traveler = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews_given')
    guide = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews_received')
    trip_area = models.ForeignKey(TripArea, on_delete=models.CASCADE, related_name='reviews', null=True, blank=True)
    rating = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        # Prevent duplicate reviews for the same guide-traveler-trip combination
        unique_together = ('traveler', 'guide', 'trip_area')
    
    def __str__(self):
        return f"Review by {self.traveler.username} for {self.guide.username}"

# New Bookmark Model
class Bookmark(models.Model):
    """Represents a bookmarked location for a user."""
    BOOKMARK_TYPES = [
        ('attraction', 'Attraction'),
        ('restaurant', 'Restaurant'),
        ('lodging', 'Accommodation'),
        ('other', 'Other'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bookmarks')
    name = models.CharField(max_length=255)
    address = models.TextField(blank=True, null=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    place_id = models.CharField(max_length=255, blank=True, null=True, unique=True) # Google Place ID, optional but useful
    type = models.CharField(max_length=20, choices=BOOKMARK_TYPES, default='other')
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('user', 'latitude', 'longitude') # Prevent duplicate bookmarks for the same location

    def __str__(self):
        return f"{self.name} ({self.user.username})"

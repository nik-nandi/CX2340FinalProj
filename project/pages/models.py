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

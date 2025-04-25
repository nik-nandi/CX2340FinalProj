from django.contrib import admin
from .models import User, TripArea, TripLocation

admin.site.register(User)
admin.site.register(TripArea)
admin.site.register(TripLocation)

from django.contrib import admin
from .models import User, TripArea, TripLocation, ItineraryItem, LocalEvent

admin.site.register(User)
admin.site.register(TripArea)
admin.site.register(TripLocation)
admin.site.register(ItineraryItem)
admin.site.register(LocalEvent)

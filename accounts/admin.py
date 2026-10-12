from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DefaultUserAdmin

from .models import Address, UserCapabilityOverride, UserProfile


User = get_user_model()


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    extra = 0
    fields = (
        "role",
        "phone_number",
        "date_of_birth",
        "gender",
        "profile_picture",
        "preferred_location_label",
        "preferred_city",
        "preferred_state",
        "preferred_pincode",
    )


admin.site.unregister(User)


@admin.register(User)
class UserAdmin(DefaultUserAdmin):
    inlines = (UserProfileInline,)
    list_display = ("username", "email", "get_role", "is_staff", "is_active")
    search_fields = ("username", "email", "first_name", "last_name", "profile__phone_number")

    @admin.display(description="Role")
    def get_role(self, obj):
        if hasattr(obj, "profile"):
            return obj.profile.get_role_display()
        return "No profile"


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "phone_number", "gender", "preferred_pincode")
    list_filter = ("role", "gender")
    search_fields = ("user__username", "user__email", "phone_number")


@admin.register(UserCapabilityOverride)
class UserCapabilityOverrideAdmin(admin.ModelAdmin):
    list_display = ("user", "capability", "is_granted", "granted_by", "updated_at")
    list_filter = ("is_granted", "capability", "updated_at")
    search_fields = ("user__username", "user__email", "capability", "reason")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("full_name", "user", "phone", "district", "city", "state", "pincode", "is_default")
    list_filter = ("address_type", "location_source", "state", "district", "city", "is_default")
    search_fields = ("full_name", "phone", "user__username", "district", "city", "pincode")
    readonly_fields = ("geocoding_payload",)

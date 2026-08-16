from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.accounts.models import Household, HouseholdMembership, User


class HouseholdMembershipInline(admin.TabularInline):
    model = HouseholdMembership
    extra = 0


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["email", "display_name", "is_staff", "is_active", "date_joined"]
    list_filter = ["is_staff", "is_superuser", "is_active"]
    search_fields = ["email", "display_name"]
    ordering = ["email"]
    inlines = [HouseholdMembershipInline]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("display_name",)}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),)


@admin.register(Household)
class HouseholdAdmin(admin.ModelAdmin):
    list_display = ["name", "currency", "created_at"]
    search_fields = ["name"]
    inlines = [HouseholdMembershipInline]

"""
accounts/views.py — Login, signup, logout views for WePet Django.
Replaces the Streamlit auth_service with standard Django auth.
Business rule preserved: email-based login, min 6-char password,
unique email enforced, redirect to /pets/ on success.
"""
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.views.decorators.http import require_http_methods


@require_http_methods(["GET", "POST"])
def login_view(request):
    """
    Combined login / signup view.
    POST field `mode` selects the branch: 'login' or 'signup'.
    """
    if request.user.is_authenticated:
        return redirect("/pets/")

    error = None
    mode = "login"
    login_email = ""
    signup_name = ""
    signup_email = ""

    if request.method == "POST":
        mode = request.POST.get("mode", "login")

        # ── LOGIN ──────────────────────────────────────────────────────
        if mode == "login":
            email = request.POST.get("email", "").strip().lower()
            password = request.POST.get("password", "")
            login_email = email

            if not email or not password:
                error = "Please enter both email and password."
            else:
                try:
                    user_obj = User.objects.get(email__iexact=email)
                    user = authenticate(
                        request,
                        username=user_obj.username,
                        password=password
                    )
                    if user is not None:
                        login(request, user)
                        return redirect("/pets/")
                    else:
                        error = "Invalid email or password."
                except User.DoesNotExist:
                    error = "No account found with that email address."

        # ── SIGN UP ────────────────────────────────────────────────────
        elif mode == "signup":
            full_name = request.POST.get("full_name", "").strip()
            email = request.POST.get("email", "").strip().lower()
            password = request.POST.get("password", "")
            confirm_password = request.POST.get("confirm_password", "")
            signup_name = full_name
            signup_email = email

            if not full_name or not email or not password:
                error = "Please fill in all required fields."
            elif password != confirm_password:
                error = "Passwords do not match."
            elif len(password) < 6:
                error = "Password must be at least 6 characters."
            elif User.objects.filter(email__iexact=email).exists():
                error = "An account with this email already exists."
            else:
                # Derive a unique username from the email prefix
                base_username = email.split("@")[0]
                username = base_username
                counter = 1
                while User.objects.filter(username=username).exists():
                    username = f"{base_username}{counter}"
                    counter += 1

                name_parts = full_name.split(" ", 1)
                first = name_parts[0]
                last = name_parts[1] if len(name_parts) > 1 else ""

                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    first_name=first,
                    last_name=last,
                )
                login(request, user)
                return redirect("/pets/")

    context = {
        "error": error,
        "mode": mode,
        "login_email": login_email,
        "signup_name": signup_name,
        "signup_email": signup_email,
    }
    return render(request, "accounts/login.html", context)


def logout_view(request):
    """Log out and redirect to login page."""
    logout(request)
    return redirect("/accounts/login/")
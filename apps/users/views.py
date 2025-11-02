from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.forms import UserCreationForm
from .models import User


def signup(request):
    """
    Регистрация нового пользователя
    """
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Регистрация прошла успешно! Добро пожаловать!')
            return redirect('dashboard:dashboard')
    else:
        form = UserCreationForm()
    
    return render(request, 'registration/signup.html', {'form': form})


@login_required
def profile(request):
    """
    Профиль пользователя
    """
    user = request.user
    
    if request.method == 'POST':
        # Обновляем профиль пользователя
        user.first_name = request.POST.get('first_name', user.first_name)
        user.last_name = request.POST.get('last_name', user.last_name)
        user.email = request.POST.get('email', user.email)
        
        user.save()
        messages.success(request, 'Профиль успешно обновлен!')
        return redirect('profile')
    
    context = {
        'user': user,
    }
    
    return render(request, 'users/profile.html', context)
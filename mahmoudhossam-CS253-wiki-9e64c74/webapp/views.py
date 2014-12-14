from django.template.response import TemplateResponse
from django.http import HttpResponse
from django.shortcuts import redirect
from utils import *

def page(request, page_name):
    page = get_page(page_name)
    logged_in = is_logged_in(request)
    if page:
        return TemplateResponse(request, 'view.html', context={'page': page,
            'logged_in': logged_in})
    else:
        return redirect('/_edit/%s' % page_name)

def main(request):
    return TemplateResponse(request, 'main.html')

def signup(request):
    signup_template = 'signup.html'

    if request.method == "GET":
        return TemplateResponse(request, signup_template)

    elif request.method == "POST":
        usr = request.POST['username']
        pw = request.POST['password']
        verify = request.POST['verify']
        email = request.POST['email']
        error_occurred = False
        c = {
                'usr': '',
                'usr_val': '',
                'email': '',
                'email_val': '',
                'pw': '',
                'pw_val': '',
                'verify': '',
                'verify_val': ''}
        if not valid_username(usr):
            c['usr'] = "This username is invalid."
            error_occurred = True
        else:
            c['usr_val'] = usr
        if not valid_email(email) and not email.strip() == "":
            c['email'] = "This email is invalid."
            error_occurred = True
        else:
            c['email_val'] = email
        if not valid_password(pw) :
            c['pw'] = "This password is inavlid."
            error_occurred = True
        else:
            c['pw_val'] = pw
        if verify != pw:
            c['verify'] = "These passwords do not match."
            error_occurred = True
        else:
            c['verify_val'] = verify
        if error_occurred:
            return TemplateResponse(request, signup_template, context=c)
        else:
            user = create_user(usr, pw, email)
            return login_success(request, user)            

def login(request):
    if request.method == 'GET':
        return TemplateResponse(request, 'login.html')
    elif request.method == 'POST':
        usr = request.POST['username']
        pw = request.POST['password']
        user = get_user(username=usr)
        if user:
            hashed = hash_password(pw, salt=user.salt)[0]
            if hashed == user.hashed_pw:
                return login_success(request, user)
        else:
            c = {'error': 'invalid login'}
            return TemplateResponse(request, 'login.html', context=c)

def edit(request, page_name):
    if is_logged_in(request):
        page = get_page(page_name)
        if request.method == 'GET':
            if page:
                return TemplateResponse(request, 'edit.html', context={'page': page})
            else:
                return TemplateResponse(request, 'edit.html', context={'page_name': page_name})

        elif request.method == 'POST':
            content = request.POST['content']
            if page:
                page.content = content
            else:
                page = Article(title=page_name, content=content)
            page.save()
            return redirect('/%s' % page_name)
    else:
        return redirect('/signup')

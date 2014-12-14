from django.conf.urls import patterns, include, url
from webapp import views

# Uncomment the next two lines to enable the admin:
# from django.contrib import admin
# admin.autodiscover()

urlpatterns = patterns('',
        url(r'^$', views.main),
        url(r'^signup$', views.signup),
        url(r'^login$', views.login),
        url(r'^_edit/(?P<page_name>[\w]+)$', views.edit),
        url(r'^(?P<page_name>[\w]+)$', views.page),
    # Examples:
    # url(r'^$', 'wiki.views.home', name='home'),
    # url(r'^wiki/', include('wiki.foo.urls')),

    # Uncomment the admin/doc line below to enable admin documentation:
    # url(r'^admin/doc/', include('django.contrib.admindocs.urls')),

    # Uncomment the next line to enable the admin:
    # url(r'^admin/', include(admin.site.urls)),
)

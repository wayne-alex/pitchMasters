from django.urls import path
from django.contrib.auth import views as auth_views


from tournament import views

urlpatterns = [
    path('login/', views.admin_login, name='adminLogin'),
    path('admin_login/', views.admin_login_view, name='adminLoginView'),
    path('admin_dashboard/', views.admin_dashboard_view, name='adminDashboardView'),
    path('admin_tournament/', views.admin_tournament_view, name='adminTournamentView'),
    path('create/', views.admin_tournament_create_view, name='adminTournamentCreateView'),
    path('<uuid:tournament_id>/edit/', views.admin_tournament_edit_view, name='adminTournamentEditView'),
    path('<uuid:tournament_id>/delete/', views.delete_tournament_view, name='adminTournamentDeleteView'),
    path('<uuid:tournament_id>/view/', views.admin_tournament_view_view, name='adminTournamentViewView'),

    path('team/add/', views.admin_team_add_view, name='adminTeamAddView'),
    path('team/<uuid:team_id>/edit/', views.admin_team_edit_view, name='adminTeamEditView'),
    path('team/<uuid:team_id>/delete/', views.admin_team_delete_view, name='adminTeamDeleteView'),
    path('team/<uuid:team_id>/view/', views.admin_team_view_view, name='adminTeamViewView'),
    path('tournament/teams/<uuid:team_id>/update/', views.admin_team_update_view, name='admin_team_update'),
    path('tournament/teams/<uuid:team_id>/assign-group/', views.admin_team_assign_group_view,
         name='admin_team_assign_group'),

    path('audit-logs/', views.admin_audit_logs_view, name='adminAuditLogsView'),

    path('system/', views.admin_system_view, name='adminSystemView'),
    path('system/users/create/', views.admin_user_create_view, name='adminUserCreateView'),
    path('system/users/<int:user_id>/delete/', views.admin_user_delete_view, name='adminUserDeleteView'),
    path('system/users/<int:user_id>/edit/', views.admin_user_edit_view, name='adminUserEditView'),

    path("<uuid:tournament_id>/fixtures/generate/", views.admin_fixture_generate_view,
         name="fixture_generate"),
    path("fixtures/<uuid:fixture_id>/score/", views.admin_fixture_score_view, name="fixture_score"),
    path("fixtures/<uuid:fixture_id>/reschedule/", views.admin_fixture_reschedule_view,
         name="fixture_reschedule"),
    path("<uuid:tournament_id>/reset/", views.admin_tournament_reset_view, name="tournament_reset"),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

]

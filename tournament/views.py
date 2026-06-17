from datetime import date

from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import IntegrityError
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from tournament.fixture_generator import FixtureGenerator
from tournament.models import Tournament, Team, AuditLog, Fixture, Group


# ==========================================
# SECURITY AUDIT LOG HELPER UTILITIES
# ==========================================

def get_client_ip(request):
    """Extracts the true client IP address, handling proxy setups."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def create_audit_entry(request, action_type, description, severity='INFO'):
    """
    Helper function to systematically provision Audit Log pipeline events.
    Fails gracefully if an unauthenticated attempt occurs.
    """
    actor = request.user if request.user and request.user.is_authenticated else None
    ip_address = get_client_ip(request)

    AuditLog.objects.create(
        actor=actor,
        action_type=action_type,
        description=description,
        severity=severity,
        ip_address=ip_address
    )


# ==========================================
# VIEWS CORE ENGINE
# ==========================================

def admin_login(request):
    return render(request, 'login.html')
@require_POST
def admin_login_view(request):
    email = request.POST.get('username') # Pulling email from the 'username' field
    password = request.POST.get('password')

    # Guardrail: Wrap the database lookup in a try/except block
    try:
        username = User.objects.get(email=email).username
    except User.DoesNotExist:
        # Assign a dummy username that will safely fail Django's authenticate step
        username = None

    # Django will gracefully return None if username is None or password is wrong
    user = authenticate(request, username=username, password=password)

    if user is not None:
        # Standard Django uses 'is_staff'. Change to 'user.staff' ONLY if it's a custom field.
        if user.is_staff:
            login(request, user)

            # Log Successful Authentication Gate
            create_audit_entry(
                request,
                action_type='AUTH_LOGIN_SUCCESS',
                description=f"Administrator session initiated successfully for user context: '{user.get_username()}'",
                severity='INFO'
            )

            return JsonResponse({
                'success': True,
                'redirect_url': '/tournament/admin_dashboard/'
            })
        else:
            # Log Authorization Failure (Valid credentials, insufficient role clearance)
            create_audit_entry(
                request,
                action_type='AUTH_ACCESS_DENIED',
                description=f"Access denied: User '{email}' authenticated successfully but lacks staff/administrative privileges.",
                severity='WARN'
            )
            return JsonResponse({
                'success': False,
                'message': 'Access Denied: Account does not have admin privileges.'
            }, status=403)

    # Log Authentication Identity Failure (Triggers safely for bad passwords OR missing emails)
    create_audit_entry(
        request,
        action_type='AUTH_LOGIN_FAILED',
        description=f"Failed authentication attempt using email identity: '{email}'",
        severity='WARN'
    )
    return JsonResponse({
        'success': False,
        'message': 'Invalid email or password.'
    }, status=401)
@login_required(login_url='/tournament/login/')
def admin_dashboard_view(request):
    tournaments = Tournament.objects.all().prefetch_related('teams', 'fixtures')
    team_list   = Team.objects.all().select_related('tournament')

    return render(request, 'admin_dashboard.html', {
        'tournament_list':      tournaments,
        'tournaments_count':    tournaments.count(),
        'team_list':            team_list,
        'total_teams_count':    team_list.count(),
        'total_fixtures_count': Fixture.objects.all().count(),
        'active_fixtures_count': Fixture.objects.filter(
            status=Fixture.Status.PLAYED
        ).count(),
        'live_fixtures': [],   # hook up later when you add live match tracking
    })

@login_required(login_url='/tournament/login/')
def admin_tournament_view(request):
    return render(request, 'admin_tournament.html')

@login_required(login_url='/tournament/login/')
def admin_tournament_create_view(request):
    if request.method == 'POST':
        tournament_name = request.POST.get('name')
        structural_format = request.POST.get('format')
        leg_mode = request.POST.get('mode')

        if not tournament_name:
            return JsonResponse({
                'success': False,
                'message': 'Tournament name is required.'
            }, status=400)

        try:
            tournament = Tournament.objects.create(
                name=tournament_name,
                format=structural_format,
                mode=leg_mode
            )

            # Log Data Insertion Provision
            create_audit_entry(
                request,
                action_type='TOURNAMENT_CREATE',
                description=f"Provisioned new tournament execution pipeline: '{tournament_name}' (Format: {structural_format}, Mode: {leg_mode})",
                severity='INFO'
            )

        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=500)

        return JsonResponse({
            'success': True,
            'message': f'Tournament "{tournament_name}" provisioned successfully!'
        }, status=200)

    return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)

@login_required(login_url='/tournament/login/')
def admin_team_add_view(request):
    if request.method == 'POST':
        tournament_id = request.POST.get('tournament_id')
        team_name = request.POST.get('team_name')
        player_name = request.POST.get('player_name')

        try:
            associated_tournament = Tournament.objects.get(id=tournament_id)
            team = Team.objects.create(name=team_name, player_name=player_name, tournament=associated_tournament)

            # Log Franchise Addition Entry
            create_audit_entry(
                request,
                action_type='TEAM_CREATE',
                description=f"Registered franchise team '{team_name}' (Manager: {player_name}) into Tournament context: '{associated_tournament.name}'",
                severity='INFO'
            )

        except Tournament.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Target parent tournament missing from system.'},
                                status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=500)

        return JsonResponse({
            'success': True,
            'message': f'Team "{team_name}" added successfully!'
        }, status=200)

    return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)

@login_required(login_url='/tournament/login/')
@require_POST
def admin_tournament_edit_view(request, tournament_id):
    try:
        tournament = Tournament.objects.get(id=tournament_id)
        old_name = tournament.name  # Keep track for descriptive tracking diffs

        tournament.name = request.POST.get('name')
        tournament.format = request.POST.get('format')
        tournament.mode = request.POST.get('mode')
        tournament.save()

        # Log Workspace Modification Warning
        create_audit_entry(
            request,
            action_type='TOURNAMENT_EDIT',
            description=f"Modified configuration states for Tournament '{old_name}' (Updated Target: '{tournament.name}')",
            severity='WARN'
        )

        return JsonResponse({
            'success': True,
            'message': 'Tournament edited Successfully'
        }, status=200)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)



@login_required(login_url='/tournament/login/')
@require_POST
def admin_team_edit_view(request, team_id):
    try:
        team = Team.objects.get(id=team_id)
        old_team_name = team.name

        tournament = Tournament.objects.get(id=request.POST.get('tournament_id'))
        team.name = request.POST.get('team_name')
        team.player_name = request.POST.get('player_name')
        team.tournament = tournament
        team.save()

        # Log Workspace Modification Warning
        create_audit_entry(
            request,
            action_type='TEAM_EDIT',
            description=f"Updated roster configuration parameters for Team '{old_team_name}' (Updated target: '{team.name}')",
            severity='WARN'
        )

        return JsonResponse({
            'success': True,
            'message': 'Team edited Successfully'
        }, status=200)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)

@login_required(login_url='/tournament/login/')
@require_POST
def delete_tournament_view(request, tournament_id):
    try:
        tournament = Tournament.objects.get(id=tournament_id)
        target_name = tournament.name  # Retain reference string before object dissociation

        tournament.delete()

        # Log Critical Database Drop Action
        create_audit_entry(
            request,
            action_type='TOURNAMENT_DELETE',
            description=f"PERMANENT CRITICAL DROP: Erased Tournament record '{target_name}' and cascades from database clusters.",
            severity='CRIT'
        )

        return JsonResponse({'success': True}, status=200)
    except Tournament.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Target record missing inside network state.'}, status=500)

@login_required(login_url='/tournament/login/')
@require_POST
def admin_team_delete_view(request, team_id):
    try:
        team = Team.objects.get(id=team_id)
        target_name = team.name  # Retain reference string before object dissociation

        team.delete()

        # Log Critical Database Drop Action
        create_audit_entry(
            request,
            action_type='TEAM_DELETE',
            description=f"PERMANENT CRITICAL DROP: Purged franchise Team record '{target_name}' from live workspace pipelines.",
            severity='CRIT'
        )

        return JsonResponse({'success': True}, status=200)
    except Team.DoesNotExist:
        return JsonResponse({
            'success': False, 'message': 'Team record missing inside network state.'
        }, status=500)

@login_required(login_url='/tournament/login/')
def admin_audit_logs_view(request):
    severity_filter = request.GET.get('severity', '')

    if severity_filter in ['INFO', 'WARN', 'CRIT']:
        logs = AuditLog.objects.filter(severity=severity_filter)
    else:
        logs = AuditLog.objects.all()

    context = {
        'logs': logs[:100],  # Slice top 100 entries for mobile optimization
        'current_filter': severity_filter,
    }
    return render(request, 'admin_audit_logs.html', context)

@login_required(login_url='/tournament/login/')
def admin_system_view(request):
    # Fetch all system users ordered by registration/ID
    users = User.objects.all().order_by('-id')
    return render(request, 'admin_system.html', {'users': users})

@login_required(login_url='/tournament/login/')
@require_POST
def admin_user_create_view(request):
    username = request.POST.get('username')
    email = request.POST.get('email')
    password = request.POST.get('password')
    role = request.POST.get('role', 'staff')

    if not username or not password:
        return JsonResponse({'success': False, 'message': 'Username and Password fields are mandatory.'}, status=400)

    if User.objects.filter(username=username).exists():
        return JsonResponse({'success': False, 'message': f"Identity conflict: '{username}' already exists."},
                            status=400)

    try:
        # Create user instance and use set_password to trigger secure PBKDF2 hashing
        user = User.objects.create_user(username=username, email=email, password=password,is_staff=True)

        # Assign custom role attribute if your architecture supports it
        if hasattr(user, 'role'):
            user.role = role
            user.save()

        # Log System Provisioning Event
        create_audit_entry(
            request,
            action_type='USER_PROVISION',
            description=f"Provisioned new system user credential space: '{username}' with role level: [{role.upper()}]",
            severity='INFO'
        )

        return JsonResponse({'success': True, 'message': f"Account '{username}' provisioned successfully!"}, status=200)

    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@require_POST
@login_required(login_url='/tournament/login/')
def admin_user_delete_view(request, user_id):
    try:
        user_to_drop = User.objects.get(id=user_id)
        target_username = user_to_drop.username

        # Self-deletion protection guardrail
        if user_to_drop == request.user:
            return JsonResponse(
                {'success': False, 'message': 'Security Constraint: You cannot terminate your own active session.'},
                status=400)

        user_to_drop.delete()

        # Log Critical Account Dropped Event
        create_audit_entry(
            request,
            action_type='USER_TERMINATE',
            description=f"CRITICAL ACCESS REVOCATION: Dropped authentication space and credentials for account: '{target_username}'",
            severity='CRIT'
        )

        return JsonResponse({'success': True}, status=200)

    except User.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Account target missing from database context.'}, status=404)


@require_POST
@login_required(login_url='/tournament/login/')
def admin_user_edit_view(request, user_id):
    try:
        user_to_edit = User.objects.get(id=user_id)
        old_username = user_to_edit.username

        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        role = request.POST.get('role')

        if not username:
            return JsonResponse({'success': False, 'message': 'Username is a required configuration property.'},
                                status=400)

        # Check for unique user collisions if updating name
        if User.objects.filter(username=username).exclude(id=user_id).exists():
            return JsonResponse(
                {'success': False, 'message': f"Collision error: Username '{username}' is already allocated."},
                status=400)

        # Apply field mutations
        user_to_edit.username = username
        user_to_edit.email = email

        if password and password.strip():
            user_to_edit.set_password(password)  # Triggers secure internal hashing pipelines

        if hasattr(user_to_edit, 'role') and role in ['admin', 'staff']:
            user_to_edit.role = role

        user_to_edit.save()

        # Log Workflow Update Warning via Helper
        create_audit_entry(
            request,
            action_type='USER_UPDATE',
            description=f"Altered account configuration indices for identity entry: '{old_username}' (Updated destination state: '{username}')",
            severity='WARN'
        )

        return JsonResponse({'success': True, 'message': 'User parameters updated successfully.'}, status=200)

    except User.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Target record missing inside network context.'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@login_required(login_url='/tournament/login/')
def admin_tournament_view_view(request, tournament_id):
    # Safe lookup: returns a clean 404 instead of throwing a 500 server crash if ID doesn't exist
    tournament = get_object_or_404(Tournament, id=tournament_id)

    # Efficiently load matches along with their relational objects in a single database trip
    fixtures = tournament.fixtures.select_related("home_team", "away_team").order_by("match_date", "round")

    # Fallback/Safety fallback: get the teams queryset to support template filters like |length
    teams = tournament.teams.all()

    context = {
        "tournament": tournament,
        "fixtures": fixtures,
        "teams": teams,  # Keeps template tags like {{ teams|length }} functional
        "teams_count": teams.count(),
        "fixtures_count": fixtures.count(),
    }

    return render(request, 'admin_view_tournament.html', context)


def _json_error(message, status=400):
    return JsonResponse({"success": False, "error": message}, status=status)


def _json_ok(message, **extra):
    return JsonResponse({"success": True, "message": message, **extra})


def _owned_tournament(request, tournament_id):
    """Return the tournament only if the requesting user created it."""
    return get_object_or_404(
        Tournament,
        id=tournament_id,

    )


# ── generate fixtures ─────────────────────────────────────────────────────────

@login_required(login_url='/tournament/login/')
@require_POST
def admin_fixture_generate_view(request, tournament_id):
    tournament = _owned_tournament(request, tournament_id)

    fmt = request.POST.get("format", "").strip()
    print(fmt)
    start_raw = request.POST.get("start_date", "").strip()
    duration = request.POST.get("duration", "").strip()
    legs = request.POST.get("legs", "1").strip()

    VALID_FORMATS = {"league", "knockout", "group_knockout", "uefa_league_phase"}

    if fmt not in VALID_FORMATS:
        return _json_error(f"Invalid format '{fmt}'.")

    if not start_raw:
        return _json_error("Start date is required.")

    try:
        start_date = date.fromisoformat(start_raw)
    except ValueError:
        return _json_error("Start date is not a valid date (expected YYYY-MM-DD).")

    try:
        duration = int(duration)
        if duration < 1:
            raise ValueError
    except ValueError:
        return _json_error("Duration must be a positive integer.")

    try:
        legs = int(legs)
        if legs not in (1, 2):
            raise ValueError
    except ValueError:
        return _json_error("Legs must be 1 or 2.")

    if tournament.teams.count() < 2:
        return _json_error("At least 2 teams must be registered before generating fixtures.")

    # ── 2. Build config dict for the generator ────────────────────
    config = {
        "start_date": start_raw,
        "duration": duration,
        "legs": legs,
    }

    # Group + Knockout extras
    if fmt == "group_knockout":
        try:
            config["groups"] = int(request.POST.get("groups", 2))
            config["qualify_per_group"] = int(request.POST.get("qualify_per_group", 2))
        except ValueError:
            return _json_error("Groups and qualify-per-group must be valid numbers.")

        if config["groups"] < 2:
            return _json_error("Must have at least 2 groups.")
        if config["qualify_per_group"] < 1:
            return _json_error("At least 1 team must qualify per group.")

    # UEFA League Phase extras
    if fmt == "uefa_league_phase":
        total_opp = request.POST.get("total_opponents", "").strip()
        if total_opp:
            try:
                config["total_opponents"] = int(total_opp)
                if config["total_opponents"] < 2:
                    raise ValueError
            except ValueError:
                return _json_error("Total opponents must be a number ≥ 2.")
        # if blank → generator auto-calculates, so we just omit the key

    # ── 3. Sync format & legs back onto the Tournament record ─────
    #    Map the form value to the Tournament.Format choices
    FORMAT_MAP = {
        "league": Tournament.Format.LEAGUE,
        "knockout": Tournament.Format.KNOCKOUT,
        "group_knockout": Tournament.Format.GROUP_AND_KNOCKOUT,
        "uefa_league_phase": Tournament.Format.UEFA_LEAGUE_PHASE,
    }
    MODE_MAP = {
        1: Tournament.Mode.SINGLE_LEG,
        2: Tournament.Mode.HOME_AWAY,
    }

    tournament.format = FORMAT_MAP[fmt]
    tournament.mode = MODE_MAP[legs]
    tournament.start_date = start_date
    tournament.status = Tournament.Status.ACTIVE
    tournament.save(update_fields=["format", "mode", "start_date", "status", "updated_at"])

    # ── 4. Run the generator ──────────────────────────────────────
    try:
        generator = FixtureGenerator(tournament, config)
        generator.generate()
    except ValueError as exc:
        return _json_error(str(exc))
    except Exception as exc:
        # Log unexpected errors but don't expose internals to the client
        create_audit_entry(
            request,
            action_type="FIXTURE_GENERATE_ERROR",
            description=f"Unhandled error generating fixtures for tournament {tournament.id}: {exc}",
            severity="CRIT",
        )
        return _json_error("An unexpected error occurred. Please try again.", status=500)

    # ── 5. Audit log ──────────────────────────────────────────────
    fixture_count = tournament.fixtures.count()
    create_audit_entry(
        request,
        action_type="FIXTURE_GENERATE",
        description=(
            f"{request.user} generated {fixture_count} fixtures for "
            f"'{tournament.name}' — format={fmt}, legs={legs}, "
            f"start={start_raw}, duration={duration}d"
        ),
        severity="WARN",  # modifying action
    )

    return _json_ok(
        f"{fixture_count} fixtures generated successfully.",
        fixture_count=fixture_count,
    )


# ── enter score ───────────────────────────────────────────────────────────────

@login_required(login_url='/tournament/login/')
@require_POST
def admin_fixture_score_view(request, fixture_id):
    fixture = get_object_or_404(
        Fixture,
        id=fixture_id,

    )

    try:
        home_score = int(request.POST["home_score"])
        away_score = int(request.POST["away_score"])
        if home_score < 0 or away_score < 0:
            raise ValueError
    except (KeyError, ValueError):
        return _json_error("Scores must be non-negative integers.")

    fixture.home_score = home_score
    fixture.away_score = away_score
    fixture.status = Fixture.Status.PLAYED
    fixture.save(update_fields=["home_score", "away_score", "status", "updated_at"])

    create_audit_entry(
        request,
        action_type="FIXTURE_SCORE",
        description=(
            f"{request.user} entered score {home_score}–{away_score} for "
            f"fixture {fixture.home_team} vs {fixture.away_team} "
            f"(tournament: {fixture.tournament.name})"
        ),
        severity="INFO",
    )

    return _json_ok("Score saved.")


# ── reschedule match ──────────────────────────────────────────────────────────

@login_required(login_url='/tournament/login/')
@require_POST
def admin_fixture_reschedule_view(request, fixture_id):
    fixture = get_object_or_404(
        Fixture,
        id=fixture_id,

    )

    date_raw = request.POST.get("match_date", "").strip()
    if not date_raw:
        return _json_error("A new date is required.")

    try:
        new_date = date.fromisoformat(date_raw)
    except ValueError:
        return _json_error("Invalid date format (expected YYYY-MM-DD).")

    old_date = fixture.match_date
    fixture.match_date = new_date
    fixture.save(update_fields=["match_date", "updated_at"])

    create_audit_entry(
        request,
        action_type="FIXTURE_RESCHEDULE",
        description=(
            f"{request.user} rescheduled {fixture.home_team} vs {fixture.away_team} "
            f"from {old_date} to {new_date} (tournament: {fixture.tournament.name})"
        ),
        severity="INFO",
    )

    return _json_ok("Match rescheduled.", new_date=str(new_date))


# ── reset fixtures ────────────────────────────────────────────────────────────

@login_required(login_url='/tournament/login/')
@require_POST
def admin_tournament_reset_view(request, tournament_id):
    tournament = _owned_tournament(request, tournament_id)

    fixture_count = tournament.fixtures.count()
    group_count = tournament.groups.count()

    Fixture.objects.filter(tournament=tournament).delete()
    Group.objects.filter(tournament=tournament).delete()

    tournament.status = Tournament.Status.DRAFT
    tournament.save(update_fields=["status", "updated_at"])

    create_audit_entry(
        request,
        action_type="TOURNAMENT_RESET",
        description=(
            f"{request.user} reset tournament '{tournament.name}' — "
            f"deleted {fixture_count} fixtures and {group_count} groups."
        ),
        severity="CRIT",
    )

    return _json_ok(f"Tournament reset. {fixture_count} fixtures deleted.")

@login_required(login_url='/tournament/login/')
def admin_team_view_view(request, team_id):
    team       = get_object_or_404(Team.objects.select_related('tournament'), id=team_id)
    tournament = team.tournament
    team_group = team.groups.filter(tournament=tournament).first()
    all_groups = Group.objects.filter(tournament=tournament)

    fixtures = Fixture.objects.filter(
        Q(home_team=team) | Q(away_team=team)
    ).select_related('home_team', 'away_team', 'group').order_by('match_date', 'round')

    # ── Calculate stats ───────────────────────────────────────
    played = wins = draws = losses = goals_for = goals_against = 0

    for f in fixtures:
        if f.status != Fixture.Status.PLAYED:
            continue
        played += 1
        is_home = (f.home_team_id == team.id)
        ts = f.home_score if is_home else f.away_score   # team score
        os = f.away_score if is_home else f.home_score   # opponent score

        if ts is not None and os is not None:
            goals_for      += ts
            goals_against  += os
            if ts > os:   wins   += 1
            elif ts == os: draws  += 1
            else:          losses += 1

    goal_diff = goals_for - goals_against
    points    = (wins * 3) + draws

    # Percentages for the W/D/L bar (avoid div-by-zero)
    win_pct  = round((wins   / played) * 100) if played else 0
    draw_pct = round((draws  / played) * 100) if played else 0
    loss_pct = 100 - win_pct - draw_pct        # absorbs rounding remainder

    context = {
        'tournament':  tournament,
        'team':        team,
        'team_group':  team_group,
        'all_groups':  all_groups,
        'fixtures':    fixtures,
        'stats': {
            'played':         played,
            'wins':           wins,
            'draws':          draws,
            'losses':         losses,
            'goals_for':      goals_for,
            'goals_against':  goals_against,
            'goal_diff':      goal_diff,
            'points':         points,
            'win_pct':        win_pct,
            'draw_pct':       draw_pct,
            'loss_pct':       loss_pct,
        }
    }
    return render(request, 'team_view.html', context)


@login_required(login_url='/tournament/login/')
@require_POST
def admin_team_update_view(request, team_id):
    """Handles the #editTeamForm endpoint with real-time audit logging."""
    team = get_object_or_404(Team, id=team_id)

    # Stash properties before mutation to craft a rich historical log statement
    old_name = team.name
    old_player = team.player_name

    team.name = request.POST.get('name', '').strip()
    team.player_name = request.POST.get('player_name', '').strip()
    team.country = request.POST.get('country', '').strip()

    founded_year = request.POST.get('founded_year')
    team.founded_year = int(founded_year) if founded_year and founded_year.isdigit() else None

    try:
        team.save()

        # Dispatch Modification Entry to Audit Pipeline
        create_audit_entry(
            request=request,
            action_type="TEAM_UPDATE",
            description=f"Modified configuration parameters for team ID {team.id}. Identity updated from '{old_name}' ({old_player}) to '{team.name}' ({team.player_name}).",
            severity="WARN"
        )
    except IntegrityError:
        error_msg = f"The controller name '{team.player_name}' is already assigned in this tournament."
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': error_msg}, status=400)
        return redirect('admin_team_view_view', team_id=team.id)

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success', 'message': 'Team profiles successfully updated.'})
    return redirect('admin_team_view_view', team_id=team.id)


@login_required(login_url='/tournament/login/')
@require_POST
def admin_team_assign_group_view(request, team_id):
    """Handles the #groupAssignmentForm endpoint with real-time audit logging."""
    team = get_object_or_404(Team, id=team_id)
    group_id = request.POST.get('group_id')

    # Resolve old state mapping for precise audit logging
    old_group = team.groups.filter(tournament=team.tournament).first()
    old_group_name = old_group.name if old_group else "Standalone / Unassigned"

    # Strip team from any existing group configurations within this specific tournament
    active_tournament_groups = team.groups.filter(tournament=team.tournament)
    for existing_group in active_tournament_groups:
        existing_group.teams.remove(team)

    # Apply configuration change matrix
    new_group_name = "Standalone / Unassigned"
    if group_id:
        target_group = get_object_or_404(Group, id=group_id, tournament=team.tournament)
        target_group.teams.add(team)
        new_group_name = target_group.name

    # Dispatch Modification Entry to Audit Pipeline
    create_audit_entry(
        request=request,
        action_type="TEAM_GROUP_ASSIGN",
        description=f"Shifted group allocation array for team '{team.name}' from cluster '{old_group_name}' to '{new_group_name}'.",
        severity="WARN"
    )

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success', 'message': 'Tournament cluster group re-allocated.'})
    return redirect('admin_team_view_view', team_id=team.id)
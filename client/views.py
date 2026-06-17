import json
import uuid
from datetime import date, timedelta

from django.http import JsonResponse
from django.shortcuts import render
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_http_methods

from client.models import DeviceUserPreference
from tournament.models import Tournament, Team, AuditLog, Fixture


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


# Create your views here.
def landing(request):
    return render(request, 'landing.html')


def favourite(request):
    if request.method == 'POST':
        try:
            payload = json.loads(request.body)
            uuid_str = payload.get("device_uuid")
            selected_tournament_ids = payload.get("tournaments", [])
            selected_team_ids = payload.get("teams", [])

            if not uuid_str:
                return JsonResponse({"error": "Missing client device reference id"}, status=400)

            # Fetch existing or spin up new preference block for this unique device tracking token
            preference, created = DeviceUserPreference.objects.get_or_create(device_uuid=uuid_str)

            # Sync relations safely
            preference.favorite_tournaments.set(Tournament.objects.filter(id__in=selected_tournament_ids))
            preference.favorite_teams.set(Team.objects.filter(id__in=selected_team_ids))

            # Audit tracking implementation
            action_verb = "Initialized" if created else "Updated"
            audit_desc = (
                f"Device {uuid_str} {action_verb.lower()} arena preferences. "
                f"Synced {len(selected_tournament_ids)} tournaments and {len(selected_team_ids)} teams."
            )
            create_audit_entry(
                request=request,
                action_type=f"PREFERENCE_{action_verb.upper()}",
                description=audit_desc,
                severity="INFO"
            )

            return JsonResponse({"status": "success", "message": "Arena settings updated safely"}, status=200)
        except Exception as e:
            # Audit failure occurrences if needed
            create_audit_entry(
                request=request,
                action_type="PREFERENCE_UPDATE_FAILED",
                description=f"Failed to update preferences for payload. Error: {str(e)}",
                severity="WARN"
            )
            return JsonResponse({"error": str(e)}, status=500)
    else:
        tournaments_qs = Tournament.objects.filter(status="active")
        tournaments_data = [
            {"id": str(t.id), "name": t.name, "category": t.category}
            for t in tournaments_qs
        ]
        teams_qs = Team.objects.all()
        teams_data = [
            {"id": str(t.id), "name": t.name, "player_name": t.player_name}
            for t in teams_qs
        ]
        return render(request, 'favourite.html', {"tournaments": tournaments_data,
                                                  "teams": teams_data})


def favourite2(request):
    return render(request, 'favourite2.html')


def dashboard(request):
    return render(request, 'dashboard.html')


def getStarted(request):
    return render(request, 'getStarted.html')


def matches_view(request):

    date_param = request.GET.get('date')
    today = date.today()

    try:
        target_date = parse_date(date_param) if date_param else today
    except (ValueError, TypeError):
        target_date = today

    date_strip = []
    for i in range(-20, 20):
        loop_date = today + timedelta(days=i)

        if loop_date == today:
            display_label = "Today"
        elif loop_date == today - timedelta(days=1):
            display_label = "Yesterday"
        elif loop_date == today + timedelta(days=1):
            display_label = "Tomorrow"
        else:
            display_label = loop_date.strftime("%a")  # e.g. "Mon"

        date_strip.append({
            'date_obj': loop_date,
            'date_str': loop_date.isoformat(),
            'label': display_label,
            'is_selected': loop_date == target_date,
        })

    # Get device UUID for favorites
    device_uuid = request.COOKIES.get('device_uuid') or request.session.get('device_uuid')
    fav_fixture_ids = []

    if device_uuid:
        try:
            pref = DeviceUserPreference.objects.filter(
                device_uuid=uuid.UUID(device_uuid)
            ).first()
            if pref:
                fav_fixture_ids = list(pref.favorite_tournaments.values_list('id', flat=True))
        except (ValueError, TypeError):
            pass

    # Fetch fixtures for the selected date
    fixtures = Fixture.objects.filter(
        match_date=target_date
    ).select_related(
        'tournament', 'home_team', 'away_team', 'group'
    ).order_by('tournament', 'round')

    # Build data structures
    all_fixtures_list = []
    competitions_map = {}
    favorites_map = {}

    for fixture in fixtures:
        # Determine if favorite
        is_fav = fixture.tournament.id in fav_fixture_ids

        # Generate tournament abbreviation
        words = fixture.tournament.name.split()
        txt_top = words[0][:2].upper() if words else "PM"
        txt_bottom = words[1][:2].upper() if len(words) > 1 else (
            words[0][2:4].upper() if len(words[0]) > 3 else "IN"
        )

        # Determine time/status label
        if fixture.status == Fixture.Status.PLAYED:
            time_label = "FT"
        elif fixture.status == "live":
            time_label = f"{fixture.live_minute}'" if hasattr(fixture, 'live_minute') else "LIVE"
        elif fixture.status == Fixture.Status.POSTPONED:
            time_label = "PPD"
        elif fixture.status == Fixture.Status.CANCELLED:
            time_label = "CAN"
        else:  # SCHEDULED
            time_label = fixture.match_date.strftime("%H:%M") if fixture.match_date else "TBD"

        is_live = fixture.status == "live"

        # Build match data
        match_data = {
            'id': str(fixture.id),
            'tournament_id': str(fixture.tournament.id),
            'tournament_name': fixture.tournament.name,
            'tournament_abbr': txt_top + txt_bottom,
            'group_label': fixture.group.name if fixture.group else f"Round {fixture.round}",
            'time_label': time_label,
            'is_live': is_live,
            'is_fav': is_fav,
            'team1_name': fixture.home_team.name,
            'team1_score': fixture.home_score if fixture.home_score is not None else "-",
            'team2_name': fixture.away_team.name,
            'team2_score': fixture.away_score if fixture.away_score is not None else "-",
            'is_selected': False,  # Will be set to first fixture
        }

        # Add to all fixtures (for carousel)
        all_fixtures_list.append(match_data)

        # Add to competitions map (for all matches tab)
        if fixture.tournament.id not in competitions_map:
            competitions_map[fixture.tournament.id] = {
                'id': str(fixture.tournament.id),
                'name': fixture.tournament.name,
                'category': fixture.tournament.category,
                'prefix_top': txt_top,
                'prefix_bottom': txt_bottom,
                'live_count': 0,
                'matches': []
            }

        competitions_map[fixture.tournament.id]['matches'].append(match_data)
        if is_live:
            competitions_map[fixture.tournament.id]['live_count'] += 1

        # Add to favorites map (for favorites tab)
        if is_fav:
            if fixture.tournament.id not in favorites_map:
                favorites_map[fixture.tournament.id] = {
                    'id': str(fixture.tournament.id),
                    'name': fixture.tournament.name,
                    'category': fixture.tournament.category,
                    'prefix_top': txt_top,
                    'prefix_bottom': txt_bottom,
                    'matches': []
                }
            favorites_map[fixture.tournament.id]['matches'].append(match_data)

    # Mark first fixture as selected
    if all_fixtures_list:
        all_fixtures_list[0]['is_selected'] = True

    context = {
        'all_fixtures': all_fixtures_list,
        'competitions': list(competitions_map.values()),
        'favorites_competitions': list(favorites_map.values()),
        'date_strip': date_strip,
        'target_date': target_date,
    }

    response = render(request, 'match.html', context)

    # Set device UUID cookie if not present
    if not device_uuid:
        new_uuid = str(uuid.uuid4())
        response.set_cookie('device_uuid', new_uuid, max_age=31536000 * 5)
        request.session['device_uuid'] = new_uuid

    return response


@require_http_methods(["POST"])
def toggle_favorite(request):
    """Toggle favorite status for a single fixture/match"""
    try:
        data = json.loads(request.body)
        fixture_id = data.get('fixture_id')

        device_uuid = request.COOKIES.get('device_uuid') or request.session.get('device_uuid')
        if not device_uuid:
            return JsonResponse({'success': False, 'error': 'No device UUID'}, status=400)

        # Get or create device preference profile
        pref, _ = DeviceUserPreference.objects.get_or_create(
            device_uuid=uuid.UUID(device_uuid)
        )

        # Look up the specific match
        fixture = Fixture.objects.get(id=fixture_id)

        # Toggle favorite status on the SINGLE match level
        if fixture in pref.favorite_fixtures.all():
            pref.favorite_fixtures.remove(fixture)
            is_fav = False
        else:
            pref.favorite_fixtures.add(fixture)
            is_fav = True

        return JsonResponse({'success': True, 'is_fav': is_fav})

    except Fixture.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Match not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


def feed_view(request):
    return render(request, 'feed.html')


def favorites_view(request):
    return render(request, 'star.html')


def news_view(request):
    return render(request, 'news.html')

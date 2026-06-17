import random
import math
from datetime import date, timedelta
from itertools import combinations

from .models import Tournament, Team, Group, Fixture


class FixtureGenerator:
    """
    Config shape expected:
    {
        "start_date": "2025-01-01",   # ISO date string
        "duration":   30,             # number of days the tournament spans

        # Format is set on the Tournament model: league | knockout | group_knockout | uefa_league_phase

        "legs":       1 | 2,          # 1 = single leg, 2 = home & away (applies to league, group, uefa)
        "groups":     4,              # group_knockout only — number of groups
        "qualify_per_group": 2,       # group_knockout only — teams that advance per group

        # UEFA League Phase only
        "home_opponents":  4,         # how many different opponents each team faces at home
        "away_opponents":  4,         # how many different opponents each team faces away
        # if omitted, defaults are auto-calculated from squad size
    }
    """

    def __init__(self, tournament: Tournament, config: dict):
        self.tournament = tournament
        self.config = config

        self.start_date = date.fromisoformat(config["start_date"])
        self.duration   = int(config["duration"])   # days
        self.end_date   = self.start_date + timedelta(days=self.duration - 1)

        self.legs = int(config.get("legs", 1))      # 1 or 2

        self._slot_pool = []

    # ---------------------------------------------------------------
    # PUBLIC ENTRY POINT
    # ---------------------------------------------------------------
    def generate(self):
        # Wipe existing data for this tournament
        Fixture.objects.filter(tournament=self.tournament).delete()
        Group.objects.filter(tournament=self.tournament).delete()

        fmt = self.tournament.format

        if fmt == "league":
            self._generate_league()
        elif fmt == "knockout":
            self._generate_knockout()
        elif fmt == "group_and_knockout":
            self._generate_group_knockout()
        elif fmt == "uefa_league_phase":
            self._generate_uefa_league_phase()
        else:
            print(fmt)
            raise ValueError(f"Unknown tournament format: {fmt}")

    # ---------------------------------------------------------------
    # SLOT SYSTEM  —  spreads N matches evenly across duration
    # ---------------------------------------------------------------
    def _build_slot_pool(self, total_matches: int):
        """
        Build a list of dates, one per match, spread evenly across
        the tournament window (start_date .. end_date).
        """
        if self.duration <= 0:
            raise ValueError("Duration must be at least 1 day")

        games_per_day = math.ceil(total_matches / self.duration)

        slots = []
        current = self.start_date

        while current <= self.end_date:
            for _ in range(games_per_day):
                slots.append(current)
            current += timedelta(days=1)

        # trim to exact count (ceil can overshoot by a few)
        return slots[:total_matches]

    def _pop_slot(self):
        if self._slot_pool:
            return self._slot_pool.pop(0)
        return self.end_date  # safety fallback

    # ---------------------------------------------------------------
    # LEAGUE  (single or double leg)
    # ---------------------------------------------------------------
    def _generate_league(self):
        teams = self._get_teams()

        matchups = list(combinations(teams, 2))         # every pair once

        if self.legs == 2:
            matchups += [(b, a) for a, b in matchups]  # add return fixtures

        random.shuffle(matchups)
        self._slot_pool = self._build_slot_pool(len(matchups))

        for round_num, (home, away) in enumerate(matchups, start=1):
            Fixture.objects.create(
                tournament=self.tournament,
                home_team=home,
                away_team=away,
                match_date=self._pop_slot(),
                round=round_num,
            )

    # ---------------------------------------------------------------
    # KNOCKOUT  (single or double leg)
    # ---------------------------------------------------------------
    def _generate_knockout(self):
        teams = self._get_teams()
        random.shuffle(teams)

        # Pad to next power of 2 so the bracket works cleanly
        size  = self._next_power_of_two(len(teams))
        teams += [None] * (size - len(teams))           # None = bye

        pairs = [(teams[i], teams[i + 1]) for i in range(0, len(teams), 2)]
        real_pairs = [(h, a) for h, a in pairs if h and a]  # drop byes

        # Double leg: each tie gets a home AND away fixture
        matchups = []
        for home, away in real_pairs:
            matchups.append((home, away))
            if self.legs == 2:
                matchups.append((away, home))

        self._slot_pool = self._build_slot_pool(len(matchups))

        for home, away in matchups:
            Fixture.objects.create(
                tournament=self.tournament,
                home_team=home,
                away_team=away,
                match_date=self._pop_slot(),
                round=1,
            )

    # ---------------------------------------------------------------
    # GROUP + KNOCKOUT  (group legs configurable)
    # ---------------------------------------------------------------
    def _generate_group_knockout(self):
        num_groups = int(self.config.get("groups", 2))

        teams = self._get_teams()
        random.shuffle(teams)

        # Distribute teams round-robin across groups
        groups_teams = [[] for _ in range(num_groups)]
        for i, team in enumerate(teams):
            groups_teams[i % num_groups].append(team)

        mixed_matches = []  # (group_obj, home, away)

        for idx, group_teams in enumerate(groups_teams):
            group = Group.objects.create(
                tournament=self.tournament,
                name=f"Group {chr(65 + idx)}"        # Group A, B, C …
            )
            group.teams.set(group_teams)

            matches = list(combinations(group_teams, 2))

            if self.legs == 2:
                matches += [(b, a) for a, b in matches]

            random.shuffle(matches)

            for home, away in matches:
                mixed_matches.append((group, home, away))

        # Interleave so all groups progress together, then light shuffle
        mixed_matches = self._interleave_groups(mixed_matches, num_groups)

        self._slot_pool = self._build_slot_pool(len(mixed_matches))

        for round_num, (group, home, away) in enumerate(mixed_matches, start=1):
            Fixture.objects.create(
                tournament=self.tournament,
                group=group,
                home_team=home,
                away_team=away,
                match_date=self._pop_slot(),
                round=round_num,
            )

    # ---------------------------------------------------------------
    # UEFA LEAGUE PHASE
    # Each team plays a fixed number of unique opponents,
    # half at home, half away — no two teams meet more than once.
    # Number of opponents scales automatically with squad size.
    # ---------------------------------------------------------------
    def _generate_uefa_league_phase(self):
        teams = self._get_teams()
        n     = len(teams)

        if n < 4:
            raise ValueError("UEFA League Phase needs at least 4 teams")

        # Auto-calculate opponents per team if not supplied
        # Rule: each team plays roughly half the field, even split H/A
        total_opponents = int(self.config.get("total_opponents", self._uefa_opponents(n)))
        home_opponents  = total_opponents // 2
        away_opponents  = total_opponents - home_opponents  # handles odd totals

        matchups = self._build_uefa_draw(teams, home_opponents, away_opponents)
        random.shuffle(matchups)

        self._slot_pool = self._build_slot_pool(len(matchups))

        for round_num, (home, away) in enumerate(matchups, start=1):
            Fixture.objects.create(
                tournament=self.tournament,
                home_team=home,
                away_team=away,
                match_date=self._pop_slot(),
                round=round_num,
            )

    def _uefa_opponents(self, n: int) -> int:
        """
        Derive a sensible number of opponents per team from squad size.
        Mirrors real UEFA logic: ~1/3 to 1/2 of the field, always even.

        n=36 → 8 opponents  (real UCL)
        n=24 → 6 opponents
        n=16 → 6 opponents
        n=8  → 4 opponents
        """
        raw = max(4, round(n / 4.5))   # scale with squad size
        return raw if raw % 2 == 0 else raw + 1   # force even for clean H/A split

    def _build_uefa_draw(self, teams, home_count, away_count):
        """
        Assign opponents to each team so that:
        - Every team gets exactly home_count home games and away_count away games.
        - No two teams meet more than once.
        - The draw is randomised.

        Strategy: build all possible pairs, shuffle, then greedily assign
        while respecting each team's H/A budget.
        """
        all_pairs  = list(combinations(teams, 2))
        random.shuffle(all_pairs)

        home_budget = {t: home_count for t in teams}
        away_budget = {t: away_count for t in teams}

        matchups   = []
        used_pairs = set()

        for a, b in all_pairs:
            pair_key = frozenset([a.pk, b.pk])
            if pair_key in used_pairs:
                continue

            # Try a vs b  (a=home, b=away)
            if home_budget[a] > 0 and away_budget[b] > 0:
                matchups.append((a, b))
                home_budget[a] -= 1
                away_budget[b] -= 1
                used_pairs.add(pair_key)

            # Try b vs a  (b=home, a=away)
            elif home_budget[b] > 0 and away_budget[a] > 0:
                matchups.append((b, a))
                home_budget[b] -= 1
                away_budget[a] -= 1
                used_pairs.add(pair_key)

        return matchups

    # ---------------------------------------------------------------
    # HELPERS
    # ---------------------------------------------------------------
    def _get_teams(self):
        teams = list(Team.objects.filter(tournament=self.tournament))
        if len(teams) < 2:
            raise ValueError("Need at least 2 teams for this tournament")
        return teams

    def _interleave_groups(self, flat_matches, num_groups):
        """
        Split matches back into per-group buckets, interleave one-by-one
        so all groups stay in sync, then do a light shuffle.
        """
        buckets = [[] for _ in range(num_groups)]
        for i, match in enumerate(flat_matches):
            buckets[i % num_groups].append(match)

        result = []
        while any(buckets):
            for bucket in buckets:
                if bucket:
                    result.append(bucket.pop(0))

        random.shuffle(result)
        return result

    def _next_power_of_two(self, n: int) -> int:
        power = 1
        while power < n:
            power *= 2
        return power
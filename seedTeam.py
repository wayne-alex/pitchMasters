# Run with:
#   python manage.py shell < seed_teams_shell.py

from tournament.models import Tournament, Team

tournament = Tournament.objects.first()
print(f"Seeding into: {tournament.name} ({tournament.id})")

TEAMS = [
    # England
    {"name": "Manchester United",      "player_name": "Man Utd",     "country": "England",     "founded_year": 1878},
    {"name": "Manchester City",        "player_name": "Man City",     "country": "England",     "founded_year": 1880},
    {"name": "Arsenal",                "player_name": "Arsenal",      "country": "England",     "founded_year": 1886},
    {"name": "Chelsea",                "player_name": "Chelsea",      "country": "England",     "founded_year": 1905},
    {"name": "Liverpool",              "player_name": "Liverpool",    "country": "England",     "founded_year": 1892},
    {"name": "Tottenham Hotspur",      "player_name": "Spurs",        "country": "England",     "founded_year": 1882},
    {"name": "Newcastle United",       "player_name": "Newcastle",    "country": "England",     "founded_year": 1892},
    {"name": "Aston Villa",            "player_name": "Villa",        "country": "England",     "founded_year": 1874},
    # Spain
    {"name": "Real Madrid",            "player_name": "R.Madrid",     "country": "Spain",       "founded_year": 1902},
    {"name": "FC Barcelona",           "player_name": "Barca",        "country": "Spain",       "founded_year": 1899},
    {"name": "Atletico Madrid",        "player_name": "Atletico",     "country": "Spain",       "founded_year": 1903},
    {"name": "Sevilla FC",             "player_name": "Sevilla",      "country": "Spain",       "founded_year": 1890},
    # Germany
    {"name": "Bayern Munich",          "player_name": "Bayern",       "country": "Germany",     "founded_year": 1900},
    {"name": "Borussia Dortmund",      "player_name": "Dortmund",     "country": "Germany",     "founded_year": 1909},
    {"name": "Bayer Leverkusen",       "player_name": "Leverkusen",   "country": "Germany",     "founded_year": 1904},
    {"name": "RB Leipzig",             "player_name": "Leipzig",      "country": "Germany",     "founded_year": 2009},
    # Italy
    {"name": "AC Milan",               "player_name": "AC Milan",     "country": "Italy",       "founded_year": 1899},
    {"name": "Inter Milan",            "player_name": "Inter",        "country": "Italy",       "founded_year": 1908},
    {"name": "Juventus",               "player_name": "Juventus",     "country": "Italy",       "founded_year": 1897},
    {"name": "AS Roma",                "player_name": "Roma",         "country": "Italy",       "founded_year": 1927},
    # France
    {"name": "Paris Saint-Germain",    "player_name": "PSG",          "country": "France",      "founded_year": 1970},
    {"name": "Olympique de Marseille", "player_name": "Marseille",    "country": "France",      "founded_year": 1899},
    # Portugal
    {"name": "Benfica",                "player_name": "Benfica",      "country": "Portugal",    "founded_year": 1904},
    {"name": "FC Porto",               "player_name": "Porto",        "country": "Portugal",    "founded_year": 1893},
    {"name": "Sporting CP",            "player_name": "Sporting",     "country": "Portugal",    "founded_year": 1906},
    # Netherlands
    {"name": "Ajax",                   "player_name": "Ajax",         "country": "Netherlands", "founded_year": 1900},
    {"name": "PSV Eindhoven",          "player_name": "PSV",          "country": "Netherlands", "founded_year": 1913},
    # Others
    {"name": "Celtic FC",              "player_name": "Celtic",       "country": "Scotland",    "founded_year": 1888},
    {"name": "Rangers FC",             "player_name": "Rangers",      "country": "Scotland",    "founded_year": 1872},
    {"name": "Club Brugge",            "player_name": "Brugge",       "country": "Belgium",     "founded_year": 1891},
    {"name": "Shakhtar Donetsk",       "player_name": "Shakhtar",     "country": "Ukraine",     "founded_year": 1936},
    {"name": "Galatasaray",            "player_name": "Galata",       "country": "Turkey",      "founded_year": 1905},
]

created = 0
skipped = 0

for t in TEAMS:
    obj, was_created = Team.objects.get_or_create(
        tournament=tournament,
        player_name=t["player_name"],
        defaults={"name": t["name"], "country": t["country"], "founded_year": t["founded_year"]},
    )
    if was_created:
        created += 1
        print(f"  ✔  {obj.name}")
    else:
        skipped += 1
        print(f"  –  {obj.name} (skipped)")

print(f"\nDone — {created} created, {skipped} skipped. Total teams: {tournament.teams.count()}")
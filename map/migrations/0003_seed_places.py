from django.db import migrations


# Cities use the same coordinates as the bundled Natural Earth dots, so they
# replace them exactly. Seas, countries and regions use representative points.
PLACES = [
    ("Москва", 55.754, 37.614),
    ("Мурманск", 68.970, 33.100),
    ("Санкт-Петербург", 59.941, 30.314),
    ("Белое море", 65.5, 36.5),
    ("Ладога", 60.85, 31.5),
    ("Нижне-Свирский заповедник", 60.653, 33.255),
    ("Териберка", 69.164, 35.145),
    ("Северный Ледовитый океан", 82.0, 60.0),
    ("Тихий океан", 10.0, 160.0),
    ("Баренцево море", 74.0, 40.0),
    ("Турция", 39.0, 35.0),
    ("ОАЭ", 24.0, 54.0),
    ("Пекин", 39.902, 116.394),
    ("Шанхай", 31.218, 121.435),
    ("Индия", 22.0, 79.0),
    ("Непал", 28.3, 84.0),
    ("Токио", 35.687, 139.749),
    ("Осака", 34.691, 135.504),
    ("Средиземное море", 35.0, 18.0),
    ("Чёрное море", 43.0, 34.0),
    ("Кавказ", 42.5, 44.0),
    ("Азовское море", 46.0, 36.5),
    ("Каспийское море", 42.0, 50.5),
    ("Баскунчак", 48.2, 46.9),
    ("Цимлянские пески", 48.019, 42.665),
    ("Дагестан", 42.3, 47.1),
    ("Молдино", 57.7478, 35.2481),
    ("Уфа", 54.792, 56.038),
    ("Сочи", 43.590, 39.730),
    ("Химедзи", 34.815, 134.685),
    ("Киото", 35.032, 135.748),
    ("Идзу", 34.9, 138.95),
    ("Нара", 34.685, 135.805),
    ("Чупа", 66.270, 33.055),
    # MSU White Sea Biological Station: https://wsbs-msu.ru/contacts/
    ("ББС", 66.566667, 33.133333),
    ("Борок", 58.0647, 38.2347),
    ("Саратов", 51.582, 46.028),
]


def seed_places(apps, schema_editor):
    place_model = apps.get_model("map", "MapPlace")
    for name, latitude, longitude in PLACES:
        place_model.objects.using(schema_editor.connection.alias).get_or_create(
            name=name, defaults={"latitude": latitude, "longitude": longitude},
        )


class Migration(migrations.Migration):
    dependencies = [("map", "0002_mapplace")]
    # Keep places and any user edits if only this data migration is rolled back.
    operations = [migrations.RunPython(seed_places, migrations.RunPython.noop)]

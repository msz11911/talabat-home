"""Natural single-item product photos for catalog thumbnails.

Photos are looked up by English term through Wikipedia's public REST API,
normalised to a white 256x256 PNG, and cached locally. If a photo is not
available the colourful item illustration from ``item_emoji`` is used instead.
"""
from __future__ import annotations

import hashlib
import io
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from PIL import Image, ImageDraw

from item_emoji import render_thumbnail as render_illustration

CACHE_DIR = Path(__file__).resolve().parent / "photo_cache"
WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"
USER_AGENT = "TalabatHome/2.0 (shared shopping list; https://talabat-home.vercel.app)"
SIZE = 256
ART_SIZE = 228
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
_LAST_REQUEST = 0.0
REQUEST_INTERVAL = 0.35

# Exact item names first. Each value is a list of Wikipedia titles to try in order.
NAME_TERMS: dict[str, list[str]] = {
    # خضار
    "طماطم": ["Tomato"], "خيار": ["Cucumber"], "جزر": ["Carrot"],
    "بطاطس": ["Potato"], "بطاطا": ["Sweet potato"],
    "بصل أبيض": ["Onion"], "بصل أحمر": ["Red onion"], "بصل أخضر": ["Spring onion"],
    "فلفل رومي": ["Bell pepper"], "فلفل الوان أحمر": ["Bell pepper"],
    "فلفل الوان أصفر": ["Bell pepper"], "فلفل حامي أحمر": ["Chili pepper"],
    "فلفل حامي أخضر": ["Green chili pepper", "Chili pepper"],
    "باذنجان رومي": ["Eggplant"], "باذنجان عروس": ["Eggplant"],
    "باذنجان أبيض": ["Eggplant"], "كوسة": ["Zucchini"], "بسلة": ["Pea"],
    "فاصوليا": ["Green bean"], "ليمون": ["Lemon"], "بنجر": ["Beetroot"],
    "فجل أحمر": ["Radish"], "ثوم بلدي": ["Garlic"], "ثوم صيني": ["Garlic"],
    "جرجير": ["Arugula"], "خضرة بقدونس": ["Parsley"], "خضرة شبت": ["Dill"],
    "خضرة كرافس": ["Celery"], "خضرة كزبرة": ["Coriander"],
    "كابوتشي": ["Cabbage"], "كرنب بلدي": ["Cabbage"], "كرنب سلطة": ["Cabbage"],
    "ملوخية": ["Jute mallow", "Molokhia", "Okra"], "سبانخ": ["Spinach"],
    "قلقاس": ["Taro"], "سلق": ["Chard"], "ذرة سكري": ["Sweet corn"],
    "بامية": ["Okra"], "بروكلي": ["Broccoli"], "نعناع": ["Mentha"],
    "ورق عنب": ["Grape leaves", "Dolma"],
    # فاكهة
    "موز": ["Banana"], "برتقال": ["Orange (fruit)"], "يوسفي": ["Mandarin orange"],
    "تفاح": ["Apple"], "جوافة": ["Guava"], "خوخ": ["Peach"], "مشمش": ["Apricot"],
    "رمان": ["Pomegranate"], "عنب": ["Grape"], "فراولة": ["Strawberry"],
    "بطيخ": ["Watermelon"], "كنتالوب": ["Cantaloupe"], "بلح برحي": ["Date fruit"],
    "بلح رطب": ["Date fruit"], "تمر": ["Date fruit"], "تين برشومي": ["Fig"],
    "تين شوكي": ["Fig"], "كاكا": ["Pear"], "كيوي": ["Kiwifruit"],
    "قشطة": ["Custard apple"], "أفوكادو": ["Avocado"], "كريز": ["Cherry"],
    "شمام": ["Cantaloupe"],
    # أجبان
    "حليب بخيرة": ["Milk"], "حليب بلدي": ["Milk"],
    "زبادى عادي": ["Yogurt"], "زبادى لايت": ["Yogurt"],
    "جبنة رودس": ["Halloumi", "Cheese"], "جبنة قريش": ["Feta"],
    "جبنة ملح خفيف": ["Feta"], "جبنة براميلي": ["Cheese"],
    "جبنة رومي وسط": ["Cheese"], "جبنة شيدر": ["Cheddar cheese"],
    "جبنة كيري طبيعي": ["Cream cheese"], "جبنة موتزاريلا": ["Mozzarella"],
    "جبنة ريكفورد": ["Ricotta"], "زبدة بقري": ["Butter"],
    "زبدة جاموسي": ["Butter"], "زبدة فيرن": ["Butter"],
    "لنشون": ["Luncheon meat", "Spam (food)"], "بسطرمة": ["Pastrami"],
    "تركي مدخن": ["Smoked turkey", "Turkey meat"], "زيتون": ["Olive"],
    "مخلل بلدي": ["Pickled cucumber"], "مخلل بوليفي": ["Pickled cucumber"],
    "سلطة جبنة": ["Cheese"], "دومتي": ["Cheese"],
    # بقالة
    "بيض أبيض": ["Egg (food)"], "بيض أحمر": ["Egg (food)"],
    "زيت عباد": ["Sunflower oil"], "زيت قلية": ["Vegetable oil"],
    "زيت ذرة": ["Corn oil"], "زيت زيتون": ["Olive oil"], "سمنة": ["Ghee"],
    "مرقة دجاج": ["Chicken soup", "Chicken stock"], "خل": ["Vinegar"],
    "صلصة": ["Tomato sauce"], "فجيتار": ["Tomato sauce"],
    "كريمة طبخ": ["Cream"], "هوت صوص": ["Hot sauce"], "كاتشاب": ["Ketchup"],
    "مايونيز": ["Mayonnaise"], "حلاوة طحينية": ["Halva"], "طحينة": ["Tahini"],
    "عسل أسود": ["Honey"], "عسل أبيض": ["Honey"],
    # عطارة
    "بخور زمرد أربيسك": ["Incense"], "دقيق الحبة الكاملة": ["Whole wheat flour", "Flour"],
    "دقيق أبيض": ["Wheat flour", "Flour"], "ملح": ["Salt"], "شوفان": ["Oats"],
    "عدس أصفر": ["Lentil"], "عدس بجبة": ["Lentil"], "فاصوليا": ["Beans"],
    "لوبيا": ["Cowpea"], "حمص شامي": ["Chickpea"], "ترمس حلو": ["Lupin"],
    "ينسون": ["Anise"], "شمر": ["Fennel"], "كراوية": ["Caraway"],
    "سحلب": ["Salep", "Milk"], "سمسم": ["Sesame"], "جنزبيل ناعم": ["Ginger"],
    "جوزة الطيب": ["Nutmeg"], "حبة البركة": ["Nigella sativa"],
    "حبهان": ["Cardamom"], "سبع بهارات": ["Mixed spice", "Spice"],
    "سماق": ["Sumac"], "شطة": ["Chili powder", "Chili pepper"],
    "ورق لوري": ["Bay leaf"], "فلفل أسود حصى": ["Black pepper"],
    "فلفل أسود ناعم": ["Black pepper"], "فول تدميس": ["Fava bean"],
    "فول مدشوش": ["Fava bean"], "قرفة عيدان": ["Cinnamon"],
    "قرفة ناعم": ["Cinnamon"], "قرنفل صحيح": ["Clove"], "قرنفل ناعم": ["Clove"],
    "كركم حصى": ["Turmeric"], "كركم ناعم": ["Turmeric"],
    "كزبرة حصى": ["Coriander seed", "Coriander"], "كزبرة ناعم": ["Coriander"],
    "كمون حصى": ["Cumin"], "كمون ناعم": ["Cumin"],
    # لحوم ودواجن وأسماك
    "لحم بلدي": ["Beef"], "لحم مفروم": ["Ground beef"], "لحم بوفتيك": ["Beef steak"],
    "دجاج كامل": ["Chicken"], "دجاج أجزاء": ["Chicken"], "دجاج بانية": ["Chicken breast"],
    "دجاج أوراك": ["Chicken thigh"], "دجاج دبوس": ["Chicken drumstick"],
    "دجاج أجنحة": ["Buffalo wing"], "دجاج قوانص": ["Chicken gizzard", "Chicken"],
    "روي دبوس": ["Turkey"], "رومي ورك": ["Turkey"],
    "مصنعات برجر": ["Hamburger"], "مصنعات ستربس": ["Chicken tender", "Chicken"],
    "مصنعات سجق": ["Sausage"], "مصنعات هوت دوج": ["Hot dog"],
    "مصنعات قلب": ["Beef heart", "Beef"], "مصنعات كبدة": ["Beef liver"],
    "مصنعات كلاوي": ["Beef kidney", "Beef"], "سمك بلطي": ["Fish"],
    "سمك فليه": ["Fish fillet", "Fish"], "جمبري": ["Shrimp"], "رنجة": ["Herring"],
    # حلواني
    "سكر أبيض": ["Sugar"], "سكر بني": ["Brown sugar", "Sugar"],
    "سكر بودر": ["Powdered sugar", "Sugar"], "سكر سويتال": ["Sugar substitute", "Sugar"],
    "زبيب": ["Raisin"], "شيكولاتة خام": ["Chocolate bar"], "عجوة": ["Date fruit"],
    "فانيليا": ["Vanilla"], "كاكاو اسباني": ["Cocoa powder"],
    "كريم شانتية": ["Whipped cream"], "كريم كراميل": ["Creme caramel", "Custard"],
    "جيلي": ["Gelatin dessert", "Jelly"], "كسترد": ["Custard"],
    "نشا": ["Cornstarch", "Starch"],
    # مخبوزات
    "عيش بلدى": ["Bread"], "عيش سن": ["Bread"], "عيش شامي": ["Pita"],
    "عيش حبه كاملة": ["Whole wheat bread", "Bread"], "عيش بكاكيم": ["Bread"],
    "فينو": ["Bread roll", "Croissant"], "كايزر": ["Bread roll", "Croissant"],
    "توست": ["Toast", "Bread"], "رقاق طري": ["Lavash", "Flatbread"],
    "سمبوسك": ["Samosa"], "كنافة": ["Kunafa"],
    # مكرونة وأرز
    "أرز بسمتي": ["Basmati rice"], "أرز بلدي": ["Rice"], "شعرية": ["Vermicelli"],
    "لسان عصفور": ["Orzo", "Pasta"], "مكرونة اسباجتي": ["Spaghetti"],
    "مكرونة خواتم": ["Pasta"], "مكرونة فرن": ["Baked pasta", "Pasta"],
    "مكرونة هلالية": ["Pasta"], "مكرونة صدف": ["Pasta shells", "Pasta"],
    # مشروبات وتسالى
    "بن": ["Coffee beans", "Coffee"], "شاي": ["Tea"], "نسكافية": ["Instant coffee", "Coffee"],
    "شاي أخضر": ["Green tea"], "شاى روبال": ["Rooibos", "Tea"],
    "شيبسي": ["Potato chip"], "فلامنجو": ["Corn chip", "Potato chip"],
    "لب أبيض": ["Sunflower seed"], "لب سوري": ["Pumpkin seed", "Sunflower seed"],
    # منظفات وأدوات منزلية
    "صابون مواعين": ["Dish soap", "Soap"], "أريال جل": ["Laundry detergent"],
    "برسيل جل أسود": ["Laundry detergent"], "داوني": ["Laundry detergent"],
    "كلوروكس جل": ["Bleach"], "معطر جليد": ["Air freshener"],
    "بخور أنسام زمرد": ["Incense"], "أسفنجة مواعين": ["Sponge (material)", "Sponge"],
    "أكياس ثلاجة صغيرة": ["Plastic bag"], "أكياس ثلاجة كبيرة": ["Plastic bag"],
    "أكياس ثلاجة وسط": ["Plastic bag"], "رول مفرش سفره": ["Tablecloth"],
    "رول قمامة": ["Trash bag", "Plastic bag"], "استريتش": ["Cling film", "Plastic wrap"],
    "فويل": ["Aluminum foil"],
    # عناية شخصية وعلاج
    "شامبو": ["Shampoo"], "شاور جل": ["Shower gel", "Body wash", "Soap"],
    "معجون أسنان": ["Toothpaste"], "ستارفيل": ["Teeth whitening", "Toothpaste"],
    "سوبت حرير": ["Body wash", "Shower gel"], "فوط صحية سوفى": ["Sanitary napkin"],
    "سرنجة": ["Syringe"], "أعشاب سيكم للقولون": ["Medicinal plant", "Herbal medicine"],
}

KEYWORD_TERMS: list[tuple[str, list[str]]] = [
    ("طماطم", ["Tomato"]), ("خيار", ["Cucumber"]), ("جزر", ["Carrot"]),
    ("بطاط", ["Potato"]), ("بصل", ["Onion"]), ("ثوم", ["Garlic"]),
    ("فلفل", ["Chili pepper", "Bell pepper"]), ("باذنجان", ["Eggplant"]),
    ("ليمون", ["Lemon"]), ("موز", ["Banana"]), ("برتقال", ["Orange (fruit)"]),
    ("تفاح", ["Apple"]), ("عنب", ["Grape"]), ("فراولة", ["Strawberry"]),
    ("بطيخ", ["Watermelon"]), ("بيض", ["Egg (food)"]), ("حليب", ["Milk"]),
    ("زباد", ["Yogurt"]), ("جبنة", ["Cheese"]), ("زبدة", ["Butter"]),
    ("عسل", ["Honey"]), ("زيت زيتون", ["Olive oil"]), ("زيت", ["Vegetable oil"]),
    ("دقيق", ["Wheat flour"]), ("ملح", ["Salt"]), ("عدس", ["Lentil"]),
    ("فاصوليا", ["Beans"]), ("لحم", ["Beef"]), ("دجاج", ["Chicken"]),
    ("سمك", ["Fish"]), ("جمبري", ["Shrimp"]), ("سكر", ["Sugar"]),
    ("شيكولاتة", ["Chocolate bar"]), ("كاكاو", ["Cocoa powder"]),
    ("عيش", ["Bread"]), ("توست", ["Bread"]), ("مكرونة", ["Pasta"]),
    ("أرز", ["Rice"]), ("شاي", ["Tea"]), ("قهوة", ["Coffee"]),
    ("بن", ["Coffee"]), ("شامبو", ["Shampoo"]), ("صابون", ["Soap"]),
    ("منظف", ["Laundry detergent"]), ("دواء", ["Blister pack"]),
    ("قرص", ["Blister pack"]), ("كبسول", ["Blister pack"]),
    ("مخلل", ["Pickle"]), ("زيتون", ["Olive"]), ("بخور", ["Incense"]),
]

GROUP_TERMS: dict[str, list[str]] = {
    "101": ["Vegetable"], "102": ["Fruit"], "103": ["Dairy product"],
    "104": ["Groceries"], "105": ["Spice"], "106": ["Meat"],
    "107": ["Confectionery"], "108": ["Bread"], "109": ["Pasta"],
    "110": ["Beverage"], "111": ["Snack food"], "112": ["Cleaning agent"],
    "113": ["Household item"], "114": ["Personal care"], "115": ["Blister pack"],
}


def terms_for(item: dict[str, Any]) -> list[str]:
    name = str(item.get("name") or "").strip()
    if name in NAME_TERMS:
        return NAME_TERMS[name]
    for needle, terms in KEYWORD_TERMS:
        if needle in name:
            return terms
    return GROUP_TERMS.get(str(item.get("group_code") or ""), ["Shopping"])


def _key(term: str) -> str:
    return hashlib.sha1(term.encode("utf-8")).hexdigest()[:20]


def _normalise(raw: bytes) -> bytes:
    with Image.open(io.BytesIO(raw)) as source:
        image = source.convert("RGBA")
        background = Image.new("RGBA", image.size, "white")
        background.alpha_composite(image)
        image = background.convert("RGB")
        image.thumbnail((ART_SIZE, ART_SIZE), Image.Resampling.LANCZOS)

    canvas = Image.new("RGB", (SIZE, SIZE), "white")
    ImageDraw.Draw(canvas).rounded_rectangle(
        (2, 2, SIZE - 3, SIZE - 3), radius=24, outline="#E7EBF1", width=2
    )
    canvas.paste(image, ((SIZE - image.width) // 2, (SIZE - image.height) // 2))
    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _get(url: str, *, params: dict[str, str] | None = None) -> requests.Response | None:
    """GET with polite throttling and retries; return None for a missing page."""
    global _LAST_REQUEST
    for attempt in range(5):
        wait = REQUEST_INTERVAL - (time.monotonic() - _LAST_REQUEST)
        if wait > 0:
            time.sleep(wait)
        _LAST_REQUEST = time.monotonic()
        try:
            response = SESSION.get(url, params=params, timeout=60)
        except requests.RequestException:
            time.sleep(1.5 * (attempt + 1))
            continue
        if response.status_code == 404:
            return None
        if response.status_code == 429 or response.status_code >= 500:
            time.sleep(2.0 * (attempt + 1))
            continue
        if response.ok:
            return response
        time.sleep(1.5 * (attempt + 1))
    return None


def _image_url_for(term: str) -> str | None:
    response = _get(
        WIKI_API,
        params={
            "action": "query",
            "titles": term,
            "prop": "pageimages",
            "piprop": "thumbnail|original",
            "pithumbsize": "500",
            "redirects": "1",
            "format": "json",
        },
    )
    if response is not None:
        try:
            pages = response.json().get("query", {}).get("pages", {})
            for page in pages.values():
                images = page.get("thumbnail") or page.get("original") or {}
                if images.get("source"):
                    return str(images["source"])
        except ValueError:
            pass

    response = _get(WIKI_SUMMARY + quote(term.replace(" ", "_"), safe="()_"))
    if response is not None:
        try:
            data = response.json()
            images = data.get("thumbnail") or data.get("originalimage") or {}
            if images.get("source"):
                return str(images["source"])
        except ValueError:
            pass
    return None


def _fetch(term: str) -> bytes | None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = CACHE_DIR / f"{_key(term)}.png"
    if cached.exists():
        return cached.read_bytes()
    missing = CACHE_DIR / f"{_key(term)}.missing"
    if missing.exists():
        return None

    image_url = _image_url_for(term)
    if not image_url:
        missing.touch()
        return None

    image_response = _get(image_url)
    if image_response is None:
        missing.touch()
        return None
    try:
        png = _normalise(image_response.content)
    except Exception:
        missing.touch()
        return None
    cached.write_bytes(png)
    return png


def render_thumbnail(item: dict[str, Any]) -> bytes:
    """Return a natural product photo, or the item illustration as fallback."""
    for term in terms_for(item):
        photo = _fetch(term)
        if photo:
            return photo
    return render_illustration(item)

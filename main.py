"""
Bot de veille Vinted - alerte Telegram sur nouvelles annonces.
Ne fait AUCUN achat automatique : il surveille et t'envoie une notif,
tu décides et tu cliques toi-même.

Conçu pour tourner en "one-shot" (un passage = une exécution), déclenché
par un scheduler externe (GitHub Actions, cron perso, etc). Le token
Telegram vient des variables d'environnement, pas du fichier de config,
pour ne jamais finir committé dans un repo.
"""

import json
import logging
import os
import random
import sys
import time
from pathlib import Path

import requests
from vinted_scraper import VintedScraper

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("vinted-bot")

CONFIG_PATH = Path(__file__).parent / "config.json"
SEEN_PATH = Path(__file__).parent / "seen_ids.json"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            "config.json introuvable. Copie config.example.json vers config.json et remplis-le."
        )
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        raise EnvironmentError(
            "Variables d'environnement TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID manquantes."
        )
    config["telegram"] = {"bot_token": bot_token, "chat_id": chat_id}
    return config


def load_seen() -> set:
    if SEEN_PATH.exists():
        return set(json.loads(SEEN_PATH.read_text(encoding="utf-8")))
    return set()


def save_seen(seen: set) -> None:
    # on garde uniquement les 5000 derniers ids pour ne pas grossir indéfiniment
    trimmed = list(seen)[-5000:]
    SEEN_PATH.write_text(json.dumps(trimmed), encoding="utf-8")


def passes_filters(item, watch: dict) -> bool:
    try:
        price = float(item.price.amount) if hasattr(item.price, "amount") else float(item.price)
    except (TypeError, ValueError, AttributeError):
        price = None

    if price is not None:
        if watch.get("min_price") is not None and price < watch["min_price"]:
            return False
        if watch.get("max_price") is not None and price > watch["max_price"]:
            return False

    title = (getattr(item, "title", "") or "").lower()

    for kw in watch.get("keywords_include", []):
        if kw.lower() not in title:
            return False

    for kw in watch.get("keywords_exclude", []):
        if kw.lower() in title:
            return False

    min_fav = watch.get("min_favourites")
    if min_fav:
        fav_count = getattr(item, "favourite_count", None)
        # certains items n'exposent pas ce champ selon l'endpoint utilisé ;
        # dans ce cas on ne bloque pas l'alerte, on ignore juste le filtre
        if fav_count is not None and fav_count < min_fav:
            return False

    return True


def sort_by_popularity(items, watch: dict):
    if not watch.get("sort_by_popularity"):
        return items
    return sorted(
        items,
        key=lambda it: getattr(it, "favourite_count", 0) or 0,
        reverse=True,
    )


def send_telegram_alert(bot_token: str, chat_id: str, watch_name: str, item) -> None:
    title = getattr(item, "title", "Annonce Vinted")
    url = getattr(item, "url", "")
    price = getattr(item, "price", "")
    photo_url = None
    photo = getattr(item, "photo", None)
    if photo:
        photo_url = getattr(photo, "url", None) or (photo.get("url") if isinstance(photo, dict) else None)

    caption = f"🔔 {watch_name}\n{title}\n💶 {price}\n{url}"

    api_base = f"https://api.telegram.org/bot{bot_token}"
    try:
        if photo_url:
            resp = requests.post(
                f"{api_base}/sendPhoto",
                data={"chat_id": chat_id, "caption": caption, "photo": photo_url},
                timeout=15,
            )
        else:
            resp = requests.post(
                f"{api_base}/sendMessage",
                data={"chat_id": chat_id, "text": caption},
                timeout=15,
            )
        if resp.status_code != 200:
            log.warning("Echec envoi Telegram (%s): %s", resp.status_code, resp.text[:200])
    except requests.RequestException as e:
        log.warning("Erreur réseau Telegram: %s", e)


def run_once(config: dict, scraper: VintedScraper, seen: set) -> int:
    new_alerts = 0
    for watch in config["watches"]:
        try:
            items = scraper.search(watch["params"])
        except Exception as e:
            log.warning("Erreur recherche '%s': %s", watch["name"], e)
            continue

        items = sort_by_popularity(items, watch)

        for item in items:
            item_id = str(getattr(item, "id", None) or getattr(item, "url", None))
            if item_id in seen:
                continue
            seen.add(item_id)

            if not passes_filters(item, watch):
                continue

            log.info("Nouvelle annonce match: %s - %s", watch["name"], getattr(item, "title", ""))
            send_telegram_alert(
                config["telegram"]["bot_token"],
                config["telegram"]["chat_id"],
                watch["name"],
                item,
            )
            new_alerts += 1

        # petite pause entre chaque recherche pour rester discret
        time.sleep(random.uniform(2, 5))

    return new_alerts


def main() -> None:
    """
    Un seul passage : charge la config, interroge chaque recherche,
    envoie les alertes, sauvegarde les ids vus, puis quitte.
    Pensé pour être relancé périodiquement par un scheduler externe
    (GitHub Actions, cron, etc.) plutôt que de tourner en boucle infinie.

    Pour un usage "process qui tourne en continu" (VPS, Raspberry Pi),
    passe --loop en argument.
    """
    config = load_config()
    seen = load_seen()
    scraper = VintedScraper(config["base_url"])

    if "--loop" in sys.argv:
        log.info("Mode boucle continue. %d recherches surveillées.", len(config["watches"]))
        while True:
            try:
                n = run_once(config, scraper, seen)
                save_seen(seen)
                if n:
                    log.info("%d nouvelle(s) alerte(s) envoyée(s).", n)
            except Exception as e:
                log.error("Erreur inattendue: %s", e)
            interval = config.get("poll_interval_seconds", 420)
            sleep_for = max(60, interval + random.uniform(-30, 30))
            log.info("Prochaine vérification dans %.0fs.", sleep_for)
            time.sleep(sleep_for)
    else:
        log.info("Passage unique. %d recherches surveillées.", len(config["watches"]))
        n = run_once(config, scraper, seen)
        save_seen(seen)
        log.info("%d nouvelle(s) alerte(s) envoyée(s).", n)


if __name__ == "__main__":
    main()

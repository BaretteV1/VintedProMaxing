# Vinted Alert Bot

Surveille des recherches Vinted et envoie une alerte Telegram sur chaque
nouvelle annonce qui matche tes critères. Aucun achat automatique : c'est
un radar, pas un acheteur.

## 1. Installation

```bash
cd vinted-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 2. Hébergement : GitHub Actions (gratuit, sans serveur)

Vercel n'est pas adapté ici : son cron gratuit ne tourne qu'une fois par jour.
GitHub Actions est gratuit et illimité sur un repo public, et lance le bot
toutes les 10 min via `.github/workflows/vinted-watch.yml` (déjà fourni).

1. Crée un repo GitHub (public, pour rester dans le gratuit) et push tout ce dossier dedans.
2. Va dans **Settings → Secrets and variables → Actions → New repository secret** et ajoute :
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
3. C'est tout — le workflow se déclenche automatiquement toutes les 10 min.
   Tu peux aussi le lancer à la main depuis l'onglet **Actions** du repo
   (bouton "Run workflow") pour tester tout de suite.

Le fichier `seen_ids.json` est recommité automatiquement par le workflow à
chaque passage, donc l'état ("déjà vu / pas vu") persiste entre les exécutions
sans base de données externe.

## 3. Créer ton bot Telegram (2 min)

1. Ouvre Telegram, cherche **@BotFather**, envoie `/newbot`, suis les instructions.
2. Il te donne un **token** (genre `123456:ABC-def...`) → à mettre dans `config.json`.
3. Envoie un message à ton nouveau bot (n'importe quoi).
4. Va sur `https://api.telegram.org/bot<TON_TOKEN>/getUpdates` dans un navigateur,
   repère `"chat":{"id": ...}` → c'est ton **chat_id**.

## 4. Configurer tes recherches

```bash
cp config.example.json config.json
```

Le token et le chat_id Telegram ne vont **pas** dans ce fichier (pour ne pas
les committer par erreur) — ils viennent des secrets GitHub / variables
d'environnement `TELEGRAM_BOT_TOKEN` et `TELEGRAM_CHAT_ID`.

Pour chaque recherche (`watches`), les champs utiles dans `params` :

| champ | rôle |
|---|---|
| `search_text` | mots-clés (ex: "carhartt wip veste") |
| `price_to` | prix max en euros |
| `brand_ids` | id numérique de la marque Vinted |
| `size_ids` | id numérique de la taille |
| `catalog_ids` | id de catégorie (ex: cartes à jouer, vestes homme...) |

**Comment trouver les `brand_ids` / `size_ids` / `catalog_ids` :**
1. Va sur vinted.fr, fais une recherche et applique tes filtres (marque, taille) à la main.
2. Ouvre les outils dev du navigateur (F12) → onglet Réseau/Network.
3. Relance la recherche, trouve la requête vers `api/v2/catalog/items`.
4. Regarde les paramètres de l'URL : tu y verras les ids numériques correspondant
   à tes filtres. Copie-les dans `config.json`.

`keywords_exclude` te sert à filtrer les trucs relous (répliques, tailles enfant, etc.)
même si Vinted les remonte dans les résultats.

`sort_by_popularity: true` trie les résultats par nombre de favoris (proxy pour
"produit tendance qui part vite") avant de les traiter — utile pour prioriser
les alertes sur les items les plus demandés. `min_favourites` permet de
carrément ignorer les annonces avec trop peu de favoris.

## 5. Tester en local (optionnel avant de passer par GitHub Actions)

```bash
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."
python3 main.py          # un seul passage, comme sur GitHub Actions
python3 main.py --loop   # boucle continue, utile pour du debug prolongé
```

## 6. Alternatives à GitHub Actions si besoin de plus de fréquence

- **Un vieux PC/Raspberry Pi à la maison** avec `main.py --loop` dans un service systemd — poll toutes les 1-2 min sans limite.
- **Railway / Render** (quelques €/mois) — process continu si tu veux du sub-10-min garanti sans dépendre d'un scheduler externe.
- Vercel + un cron externe gratuit (cron-job.org) qui appelle une route Vercel : possible, mais plus complexe à mettre en place (stockage d'état externe requis) pour un gain minime par rapport à GitHub Actions.

## Limites à connaître

- Vinted n'a pas d'API officielle : ce bot scrape le site public. Ça peut casser
  du jour au lendemain si Vinted change sa protection anti-bot — c'est la vie
  d'un projet comme celui-ci, pas un bug de ton côté.
- Reste raisonnable sur la fréquence de polling (garde >= 5 min) pour éviter
  de te faire bloquer ou, pire, flag ton compte perso si tu es connecté avec.
- C'est un outil d'alerte perso, pas destiné à être revendu/partagé à grande échelle.

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "pingvault" / "assets" / "icons"
UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/json,image/*,*/*",
}


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def save(gid: str, data: bytes, tag: str) -> None:
    for path in OUT.glob(f"{gid}.*"):
        path.unlink(missing_ok=True)
    ext = ".png" if data[:4] == b"\x89PNG" else ".jpg"
    (OUT / f"{gid}{ext}").write_bytes(data)
    print(f"saved {gid} ({tag}) {len(data)}{ext}")


def og_image(page_url: str) -> str | None:
    html = fetch(page_url).decode("utf-8", "ignore")
    patterns = [
        r'property=["\']og:image["\']\s+content=["\']([^"\']+)',
        r'content=["\']([^"\']+)["\']\s+property=["\']og:image["\']',
        r'"og:image"\s*:\s*"([^"]+)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def steam_cover(appid: int) -> bytes | None:
    bases = [
        "https://cdn.cloudflare.steamstatic.com/steam/apps",
        "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps",
    ]
    paths = [
        "library_600x900.jpg",
        "library_600x900_2x.jpg",
        "library_capsule.jpg",
        "portrait.png",
        "header.jpg",
    ]
    for base in bases:
        for path in paths:
            try:
                data = fetch(f"{base}/{appid}/{path}")
                if len(data) > 8000:
                    return data
            except Exception:
                continue
    return None


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    # Known-good Steam IDs for covers
    steam_ids = {
        "cs2": 730,
        "apex": 1172470,
        "pubg": 578080,
        "dota2": 570,
        "gta5": 271590,
        "rdr2": 1174180,
        "r6": 359550,
        "destiny2": 1085660,
        "thefinals": 2073850,
        "marvelrivals": 2767030,
        "helldivers2": 553850,
        "eafc": 2669320,
        "phasmophobia": 739630,
        "ffxiv": 39210,
        "throneandliberty": 2429640,
        "newworld": 1063730,
        "wukong": 2358720,
        "bg3": 1086940,
        "cyberpunk": 1091500,
        "diablo4": 2344520,
        "poe": 238960,
        "warframe": 230410,
        "mhw": 582010,
        "palworld": 1623730,
        "rust": 252490,
        "ark": 2399830,
        "lethalcompany": 1966720,
        "naraka": 1203220,
        "sf6": 1364780,
        "tekken8": 1778820,
        "amongus": 945360,
        "fallguys": 1097150,
        "tf2": 440,
        "l4d2": 550,
        "battlefield": 1517290,
        "cod": 1938090,
        "dbd": 381210,
        "rocketleague": 252950,
        "lostark": 1599340,
        "eldenring": 1245620,
        "zzz": 4162040,
        "tarkov": 3932890,
        "deltaforce": 2507950,
        # Expansion batch
        "mhwwilds": 2246340,
        "poe2": 2694490,
        "deadlock": 1422450,
        "seaofthieves": 1172620,
        "valheim": 892970,
        "huntshowdown": 594650,
        "deeprock": 548430,
        "oncehuman": 2139460,
        "firstdescendant": 2074920,
        "fragpunk": 2943870,
        "arenabreakout": 2078440,
        "maplestory": 216150,
        "blackdesert": 582660,
        "gw2": 1284210,
        "stardew": 413150,
        "terraria": 105600,
        "hades2": 1145350,
        "forza5": 1551360,
        "nba2k": 2878980,
        "mk1": 1971870,
        "ggst": 1384160,
        "aoe4": 1466860,
        "dayz": 221100,
        "readyornot": 1144200,
        "balatro": 2379780,
        "satisfactory": 526870,
        "nomanssky": 275850,
        "smite2": 2437570,
        "brawlhalla": 291550,
        "contentwarning": 2881650,
        "warzone": 1962663,
    }

    for gid, appid in steam_ids.items():
        data = steam_cover(appid)
        if data:
            save(gid, data, f"steam:{appid}")
        else:
            print(f"missing steam {gid}")

    # Official pages for non-steam / hard cases
    pages = {
        "genshin": "https://genshin.hoyoverse.com/en-us/",
        "hsr": "https://hsr.hoyoverse.com/en-us/",
        "roblox": "https://www.roblox.com/",
        "minecraft": "https://www.minecraft.net/en-us",
        "tft": "https://teamfighttactics.leagueoflegends.com/en-us/",
        "valorant": "https://playvalorant.com/en-us/",
        "lol": "https://www.leagueoflegends.com/en-us/",
        "fortnite": "https://www.fortnite.com/",
        "overwatch2": "https://overwatch.blizzard.com/en-us/",
        "wow": "https://worldofwarcraft.blizzard.com/en-us/",
        "osu": "https://osu.ppy.sh/home",
        "wutheringwaves": "https://wutheringwaves.kurogames.com/en/",
        "honkai3": "https://honkaiimpact3.hoyoverse.com/global/en-us/",
        "identityv": "https://idv.163.com/",
        "sc2": "https://starcraft2.blizzard.com/en-us/",
    }

    for gid, page in pages.items():
        try:
            image = og_image(page)
            if not image:
                print(f"no og {gid}")
                continue
            if image.startswith("//"):
                image = "https:" + image
            data = fetch(image)
            if len(data) > 3000:
                save(gid, data, "og:" + page)
            else:
                print(f"small og {gid} {len(data)}")
        except Exception as exc:
            print(f"og fail {gid}: {exc}")

    # specs.gg fallback for remaining
    specs = {
        "valorant": "valorant_preview.jpg",
        "lol": "league of legends_preview.jpg",
        "fortnite": "fortnite_preview.jpg",
        "overwatch2": "overwatch_preview.jpg",
        "wow": "warcraft_preview.jpg",
        "cs2": "cs2_preview.jpg",
        "apex": "apex legends_preview.jpg",
        "pubg": "pubg_preview.jpg",
        "dota2": "dota 2_preview.jpg",
        "r6": "rainbow six_preview.jpg",
        "rocketleague": "rocket league_preview.jpg",
    }
    existing = {p.stem for p in OUT.glob("*")}
    games = json.loads(
        (Path(__file__).resolve().parents[1] / "pingvault" / "data" / "games.json").read_text(
            encoding="utf-8"
        )
    )
    for game in games:
        gid = game["id"]
        if gid in existing and (OUT / f"{gid}.jpg").exists() or (OUT / f"{gid}.png").exists():
            # refresh only if tiny/wrong later; keep if already present after this run
            pass
        if any(OUT.glob(f"{gid}.*")):
            continue
        if gid in specs:
            url = "https://specs.gg/assets/img/games/" + urllib.parse.quote(specs[gid])
            try:
                save(gid, fetch(url), "specs")
            except Exception as exc:
                print(f"specs fail {gid}: {exc}")

    missing = [g["id"] for g in games if not any(OUT.glob(f'{g["id"]}.*'))]
    print("total", len(list(OUT.glob("*"))))
    print("missing", missing)


if __name__ == "__main__":
    main()

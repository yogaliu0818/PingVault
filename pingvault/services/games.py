from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Game:
    id: str
    name: str
    genre: str
    process_names: tuple[str, ...] = field(default_factory=tuple)
    ping_host: str = "1.1.1.1"
    color: str = "#3B82F6"
    aliases: tuple[str, ...] = field(default_factory=tuple)

    def search_blob(self) -> str:
        parts = [self.id, self.name, self.genre, *self.aliases, *self.process_names]
        return " ".join(parts).lower()


# Common Chinese / shorthand aliases so search works the way players type.
_ALIAS_MAP: dict[str, tuple[str, ...]] = {
    "valorant": ("瓦羅蘭", "无洛兰特", "特戰英豪", "特战英豪"),
    "lol": ("英雄聯盟", "英雄联盟", "台服lol", "聯盟"),
    "tft": ("雲頂", "云顶", "雲頂之弈", "云顶之弈"),
    "cs2": ("CS", "CSGO", "絕對武力", "反恐精英"),
    "apex": ("Apex", "頂尖命運"),
    "fortnite": ("要塞英雄", "堡垒之夜"),
    "genshin": ("原神", "Genshin"),
    "hsr": ("星穹鐵道", "星穹铁道", "崩壞星穹鐵道", "崩坏星穹铁道"),
    "zzz": ("絕區零", "绝区零"),
    "pubg": ("吃雞", "吃鸡", "絕地求生", "绝地求生"),
    "overwatch2": ("鬥陣", "守望先锋", "OW", "OW2"),
    "dota2": ("刀塔", "Dota"),
    "roblox": ("羅布樂思", "罗布乐思"),
    "minecraft": ("當個創世神", "我的世界", "MC"),
    "gta5": ("GTA", "俠盜獵車手", "侠盗猎车手"),
    "rdr2": ("碧血狂殺", "荒野大镖客"),
    "cod": ("決勝時刻", "使命召唤", "COD"),
    "r6": ("虹彩六號", "彩虹六号", "圍攻"),
    "wow": ("魔獸世界", "魔兽世界", "WOW"),
    "ffxiv": ("最終幻想14", "FF14", "FFXIV"),
    "eldenring": ("艾爾登法環", "艾尔登法环"),
    "wukong": ("黑神話", "黑神话", "悟空"),
    "bg3": ("柏德之門", "博德之门"),
    "cyberpunk": ("電馭叛客", "赛博朋克", "2077"),
    "diablo4": ("暗黑破壞神", "暗黑破坏神", "D4"),
    "poe": ("流亡黯道", "流放之路"),
    "palworld": ("幻獸帕魯", "幻兽帕鲁"),
    "osu": ("osu", "音遊"),
    "sf6": ("快打旋風", "街头霸王", "SF6"),
    "tekken8": ("鐵拳", "铁拳"),
    "tarkov": ("塔科夫", "EFT"),
    "marvelrivals": ("漫威爭鋒", "漫威争锋"),
    "deltaforce": ("三角洲", "Delta"),
    "wutheringwaves": ("鳴潮", "鸣潮", "WW"),
    "mhwwilds": ("魔物獵人荒野", "怪物猎人荒野", "猛漢", "Wilds"),
    "poe2": ("流亡黯道2", "流放之路2", "POE2"),
    "deadlock": ("Deadlock", "閥門MOBA"),
    "warzone": ("戰區", "战区", "COD戰區"),
    "seaofthieves": ("盜賊之海", "盗贼之海"),
    "valheim": ("英靈神殿", "英灵殿"),
    "huntshowdown": ("獵殺對決", "猎杀对决"),
    "deeprock": ("深岩銀河", "深岩银河", "DRG"),
    "oncehuman": ("一旦人類", "Once Human", "末日生存"),
    "firstdescendant": ("第一後裔", "第一后裔"),
    "fragpunk": ("FragPunk", "碎片朋克"),
    "arenabreakout": ("暗區突圍", "暗区突围", "ABI"),
    "maplestory": ("楓之谷", "冒险岛", "楓谷"),
    "blackdesert": ("黑色沙漠", "黑沙", "BDO"),
    "gw2": ("激戰2", "激战2", "GW2"),
    "stardew": ("星露穀物語", "星露谷", "牧場"),
    "terraria": ("Terraria", "泰拉瑞亞", "泰拉"),
    "hades2": ("黑帝斯2", "哈迪斯2"),
    "forza5": ("極限競速地平線5", "地平線5", "FH5"),
    "nba2k": ("NBA", "2K"),
    "mk1": ("真人快打", "MK1"),
    "ggst": ("罪惡裝備", "GGST", "Strive"),
    "sc2": ("星海爭霸2", "星际争霸2", "SC2"),
    "aoe4": ("世紀帝國4", "帝国时代4", "AOE4"),
    "dayz": ("DayZ", "生存之日"),
    "readyornot": ("Ready or Not", "準備好了沒"),
    "balatro": ("Balatro", "小丑牌"),
    "satisfactory": ("滿意工廠", "幸福工厂"),
    "nomanssky": ("無人深空", "无人深空", "NMS"),
    "identityv": ("第五人格", "Identity V"),
    "honkai3": ("崩壞3", "崩坏3", "崩三"),
    "smite2": ("神之浩劫2", "Smite2"),
    "brawlhalla": ("Brawlhalla", "格鬥大廳"),
    "contentwarning": ("Content Warning", "內容警告"),
}


class GameCatalog:
    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            from pingvault.services.paths import package_data_dir

            path = package_data_dir() / "games.json"
        self._path = path
        self._games = self._load()

    def _load(self) -> list[Game]:
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        games: list[Game] = []
        for item in raw:
            game_id = item["id"]
            aliases = tuple(item.get("aliases", ())) + _ALIAS_MAP.get(game_id, ())
            games.append(
                Game(
                    id=game_id,
                    name=item["name"],
                    genre=item.get("genre", "Game"),
                    process_names=tuple(item.get("process_names", [])),
                    ping_host=item.get("ping_host", "1.1.1.1"),
                    color=item.get("color", "#3B82F6"),
                    aliases=aliases,
                )
            )
        return games

    def all(self) -> list[Game]:
        return list(self._games)

    def search(self, query: str) -> list[Game]:
        q = query.strip().lower()
        if not q:
            return self.all()
        tokens = [t for t in q.replace("　", " ").split() if t]
        if not tokens:
            return self.all()
        results: list[Game] = []
        for game in self._games:
            blob = game.search_blob()
            if all(token in blob for token in tokens):
                results.append(game)
        return results

    def get(self, game_id: str) -> Game | None:
        for game in self._games:
            if game.id == game_id:
                return game
        return None

import discord
from discord.ext import commands
import os
import json
import random
from keep_alive import keep_alive
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.environ('DISCORD_BOT_TOKEN')

# ─── Persistence Snippet ───────────────────────────────────────────────────────
DATA_FILE = "game_state.json"


def load_state():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    # initial structure includes an empty active_battle
    return {"players": {}, "active_battle": None}


def save_state(state):
    with open(DATA_FILE, "w") as f:
        json.dump(state, f, indent=2)


game_state = load_state()
# ────────────────────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

resources = ["wood", "brick", "sheep", "wheat", "ore", "gold"]


# Helper
def has_resources(hand, cost):
    return all(hand.get(r, 0) >= cost[r] for r in cost)


def deduct_resources(hand, cost):
    for r in cost:
        hand[r] -= cost[r]


@bot.command()
async def join(ctx):
    uid = str(ctx.author.id)
    if uid not in game_state["players"]:
        game_state["players"][uid] = {
            "name": ctx.author.name,
            "hand": {
                r: 0
                for r in resources
            },
            "buildings": {}  # Now blank: will be filled per dice/resource
        }
        save_state(game_state)
        await ctx.send(f"{ctx.author.name} joined the game.")
    else:
        await ctx.send("You're already in the game.")


@bot.command()
async def show_hand(ctx):
    uid = str(ctx.author.id)
    if uid in game_state["players"]:
        p = game_state["players"][uid]
        hand_str = ", ".join(f"{k}: {v}" for k, v in p["hand"].items())
        build_str = ", ".join(f"{k}: {v}" for k, v in p["buildings"].items())
        await ctx.send(
            f"{ctx.author.name}'s hand: {hand_str}\nBuildings: {build_str}")
    else:
        await ctx.send("Join the game first using `!join`.")


@bot.command()
async def add_resource(ctx, resource: str, amount: int):
    uid = str(ctx.author.id)
    res = resource.lower()
    if uid in game_state["players"] and res in resources:
        game_state["players"][uid]["hand"][res] += amount
        save_state(game_state)
        await ctx.send(f"Added {amount} {res} to {ctx.author.name}.")
    else:
        await ctx.send("Invalid resource or you haven't joined.")


@bot.command()
async def remove_resource(ctx, resource: str, amount: int):
    uid = str(ctx.author.id)
    res = resource.lower()
    if uid in game_state["players"] and res in resources:
        hand = game_state["players"][uid]["hand"]
        hand[res] = max(0, hand[res] - amount)
        save_state(game_state)
        await ctx.send(f"Removed {amount} {res} from {ctx.author.name}.")
    else:
        await ctx.send("Invalid resource or you haven't joined.")


@bot.command()
async def build(ctx, structure: str, *args):
    uid = str(ctx.author.id)
    if uid not in game_state["players"]:
        return await ctx.send("Join the game first.")

    player = game_state["players"][uid]
    cost_table = {
        "settlement": {
            "wood": 1,
            "brick": 1,
            "sheep": 1,
            "wheat": 1
        },
        "city": {
            "wheat": 2,
            "ore": 3
        },
        "fortress": {
            r: 2
            for r in ["wood", "brick", "sheep", "wheat", "ore"]
        },
        "road": {
            "wood": 1,
            "brick": 1
        }
    }

    struct = structure.lower()
    if struct not in cost_table:
        return await ctx.send("Invalid structure type.")

    # Validate args length
    if len(args) % 2 != 0:
        return await ctx.send(
            "Provide number-resource pairs like: `8 wheat 10 brick`")

    # Deduct resources once
    if not has_resources(player["hand"], cost_table[struct]):
        return await ctx.send(f"Not enough resources to build a {struct}.")
    deduct_resources(player["hand"], cost_table[struct])

    # Register the structure under each (number, resource) pair
    buildings = player.setdefault("buildings", {})
    for i in range(0, len(args), 2):
        try:
            number = str(int(args[i]))
            resource = args[i + 1].lower()
        except:
            return await ctx.send("Invalid number/resource format.")

        if resource not in resources:
            return await ctx.send(f"Invalid resource: {resource}")

        if number not in buildings:
            buildings[number] = {}
        if resource not in buildings[number]:
            buildings[number][resource] = {
                "settlement": 0,
                "city": 0,
                "fortress": 0
            }

        # Ensure structure keys exist
        for s in ["settlement", "city", "fortress"]:
            buildings[number][resource].setdefault(s, 0)

        buildings[number][resource][struct] += 1

    save_state(game_state)

    summary = ", ".join(f"{args[i]} for {args[i+1]}"
                        for i in range(0, len(args), 2))
    await ctx.send(f"{ctx.author.name} built a {struct} on: {summary}")


@bot.command()
async def destroy(ctx, structure: str, *args):
    uid = str(ctx.author.id)
    if uid not in game_state["players"]:
        return await ctx.send("Join the game first.")

    player = game_state["players"][uid]
    struct = structure.lower()

    valid_structs = ["settlement", "city", "fortress"]
    if struct not in valid_structs:
        return await ctx.send(
            "Invalid structure type. Must be settlement, city, or fortress.")

    # Validate number-resource pairs
    if len(args) % 2 != 0:
        return await ctx.send(
            "Provide number-resource pairs like: `8 wheat 10 brick`")

    buildings = player.get("buildings", {})
    removed_from = []

    for i in range(0, len(args), 2):
        try:
            number = str(int(args[i]))
            resource = args[i + 1].lower()
        except:
            return await ctx.send("Invalid number/resource format.")

        if resource not in resources:
            return await ctx.send(f"Invalid resource: {resource}")

        if (number in buildings and resource in buildings[number]
                and struct in buildings[number][resource]
                and buildings[number][resource][struct] > 0):
            buildings[number][resource][struct] -= 1
            removed_from.append(f"{number} for {resource}")
        else:
            return await ctx.send(
                f"You don't have a {struct} at {number} for {resource}.")

    save_state(game_state)

    summary = ", ".join(removed_from)
    await ctx.send(f"{ctx.author.name} destroyed a {struct} on: {summary}")


@bot.command()
async def roll(ctx):
    d1, d2 = random.randint(1, 6), random.randint(1, 6)
    total = str(d1 + d2)  # keys in JSON are strings
    output = [f"Rolled {d1} + {d2} = **{total}**"]

    if total == 7:
        return

    for uid, player in game_state["players"].items():
        hand = player["hand"]
        buildings = player.get("buildings", {})
        resource_yielded = False

        if total in buildings:
            for resource, btypes in buildings[total].items():
                amount = (btypes.get("settlement", 0) * 1 +
                          btypes.get("city", 0) * 2 +
                          btypes.get("fortress", 0) * 3)
                hand[resource] += amount
                if amount > 0:
                    output.append(
                        f"{player['name']} gains {amount} {resource}")
                    resource_yielded = True

        if not resource_yielded:
            hand["gold"] += 1
            output.append(
                f"{player['name']} has no buildings on {total} +1 gold")

    save_state(game_state)
    await ctx.send("\n".join(output))


@bot.command()
async def battle(ctx, attacker_count: int, defender_count: int):
    """Start a battle and save its context, so it can be canceled."""
    attacker_id = str(ctx.author.id)
    # store who started and their troop counts
    game_state["active_battle"] = {
        "attacker": attacker_id,
        "attacker_count": attacker_count,
        "defender_count": defender_count
    }
    save_state(game_state)

    await ctx.send(
        f"**Battle initiated by {ctx.author.name}!**\n"
        f"Attacker troops: {attacker_count}\n"
        f"Defender troops: {defender_count}\n\n"
        "Manually roll up to 3 dice for attacker and up to 2 for defender. "
        "Ties go to defender. Type `!cancel` to cancel this battle.")


@bot.command()
async def fight(ctx):
    """
    Resolve one round of the active battle with automatic dice rolls.
    Rolls up to 3 dice for attacker, up to 2 for defender based on troops.
    """
    ab = game_state.get("active_battle")
    if not ab:
        return await ctx.send("There is no active battle to resolve.")

    user_id = str(ctx.author.id)
    # Allow attacker or defender to run fight:
    if user_id not in [
            ab["attacker"]
    ]:  # If you want defender too, add their ID here when known
        return await ctx.send(
            "Only the attacker can resolve the battle for now.")

    attacker_troops = ab["attacker_count"]
    defender_troops = ab["defender_count"]

    # Number of dice each rolls
    a_dice = min(3, attacker_troops)
    d_dice = min(2, defender_troops)

    # Roll dice
    a_rolls = sorted([random.randint(1, 6) for _ in range(a_dice)],
                     reverse=True)
    d_rolls = sorted([random.randint(1, 6) for _ in range(d_dice)],
                     reverse=True)

    # Compare dice
    comparisons = min(len(a_rolls), len(d_rolls))
    a_losses = 0
    d_losses = 0
    report = [
        f"Attacker rolls: {', '.join(map(str, a_rolls))}",
        f"Defender rolls: {', '.join(map(str, d_rolls))}"
    ]

    for i in range(comparisons):
        a = a_rolls[i]
        d = d_rolls[i]
        if d >= a:
            a_losses += 1
            report.append(
                f"Defender {d} beats Attacker {a} → Attacker loses 1 troop")
        else:
            d_losses += 1
            report.append(
                f"Attacker {a} beats Defender {d} → Defender loses 1 troop")

    # Update troop counts
    ab["attacker_count"] = max(0, attacker_troops - a_losses)
    ab["defender_count"] = max(0, defender_troops - d_losses)

    # Check if battle ended
    if ab["attacker_count"] == 0:
        game_state["active_battle"] = None
        save_state(game_state)
        report.append("Attacker has no troops left. Battle ends.")
    elif ab["defender_count"] == 0:
        game_state["active_battle"] = None
        save_state(game_state)
        report.append("Defender has no troops left. Battle ends.")
    else:
        save_state(game_state)
        report.append(
            f"Remaining troops — Attacker: {ab['attacker_count']} | Defender: {ab['defender_count']}"
        )

    await ctx.send("\n".join(report))


@bot.command()
async def cancel(ctx):
    """Allow the attacker to cancel the active battle."""
    ab = game_state.get("active_battle")
    if not ab:
        return await ctx.send("There is no active battle to cancel.")
    if str(ctx.author.id) != ab["attacker"]:
        return await ctx.send("Only the attacker can cancel this battle.")

    game_state["active_battle"] = None
    save_state(game_state)
    await ctx.send("Battle has been canceled by the attacker.")


keep_alive()
bot.run("TOKEN")

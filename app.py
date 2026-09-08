"""Solo TTRPG Tools - Flask Application."""

import os
from flask import Flask, Response, jsonify, redirect, render_template, request, url_for
from config import Config
from database import get_db
from dungeon_engine import DungeonEngine, DungeonState, format_dungeon_time
from emulator_engine import EmulatorEngine, get_emulator_engine
from table_loader import get_table_manager

app = Flask(__name__)
app.config.from_object(Config)

# Initialize database and table manager
db = get_db(app.config["DATABASE_PATH"])
table_manager = get_table_manager(app.config["DATA_DIR"])
engine = DungeonEngine(table_manager)
emulator = get_emulator_engine(app.config["DATA_DIR"])


@app.context_processor
def inject_globals():
    return {
        "debug_rolls": app.config.get("DEBUG_DUNGEON_ROLLS", False),
        "format_time": format_dungeon_time,
    }


# ==========================================
# MAIN MENU
# ==========================================

@app.route("/")
def index():
    """Main Solo TTRPG Tools menu."""
    return render_template("index.html")


# ==========================================
# HEXROLL 3 SANDBOX & VTT
# ==========================================

@app.route("/hexroll")
def hexroll_view():
    """Hexroll 3 Sandbox and VTT interface."""
    hexroll_url = app.config.get(
        "HEXROLL_URL",
        "/xpra/",
    )
    return render_template("hexroll.html", hexroll_url=hexroll_url)


# ==========================================
# DUNGEON CRAWLER MENU
# ==========================================

@app.route("/dungeon")
def dungeon_menu():
    """Dungeon Crawler launcher and saved games list."""
    dungeons = db.list_dungeons()
    return render_template("dungeon_menu.html", dungeons=dungeons)


@app.route("/dungeon/new", methods=["GET", "POST"])
def dungeon_new():
    """Create a new dungeon."""
    if request.method == "POST":
        dungeon_type = request.form.get("dungeon_type", "Tomb").strip()
        name = request.form.get("name", "").strip()
        size = request.form.get("size", "Medium").strip()

        # Handle Random Type
        if dungeon_type.lower() == "random":
            dungeon_type = engine.resolve_random_type()

        # Handle Random Size
        if size.lower() == "random":
            size = engine.resolve_random_size()

        # Handle Random / Empty Name
        if not name:
            name = engine.generate_dungeon_name(dungeon_type)

        hidden_floors = engine.determine_hidden_floors(size)

        dungeon = DungeonState(
            name=name,
            dungeon_type=dungeon_type,
            size=size,
            current_level=1,
            hidden_total_levels=hidden_floors,
            current_room_number=1,
            elapsed_minutes=0,
            tension_dice=0,
            progress_points=0,
            is_complete=False,
        )

        dungeon_id = db.create_dungeon(dungeon)
        dungeon.id = dungeon_id

        # Immediately generate the Entrance Room (no progress roll)
        entrance_room = engine.generate_entrance_room(dungeon)
        room_id = db.save_room(entrance_room)
        entrance_room.id = room_id

        dungeon.current_room_id = room_id
        db.update_dungeon(dungeon)

        # Initial Log Entry
        db.add_log_entry(
            dungeon_id=dungeon_id,
            elapsed_minutes=0,
            entry=f"Entered {dungeon.name} ({dungeon.dungeon_type}). Arrived at Entrance: {entrance_room.title}.",
        )

        return redirect(url_for("dungeon_play", dungeon_id=dungeon_id))

    # GET request
    dungeon_types = ["Tomb", "Cave", "Fort", "Temple", "Ruins", "Sewers", "Random"]
    sizes = ["Random", "Small", "Medium", "Large"]
    default_name = engine.generate_dungeon_name("Tomb")
    return render_template("dungeon_new.html", dungeon_types=dungeon_types, sizes=sizes, default_name=default_name)


@app.route("/api/random-name")
def api_random_name():
    """Returns a generated name based on the specified dungeon type."""
    dtype = request.args.get("type", "Tomb")
    if dtype.lower() == "random":
        dtype = engine.resolve_random_type()
    name = engine.generate_dungeon_name(dtype)
    return jsonify({"name": name, "dungeon_type": dtype})


# ==========================================
# DUNGEON PLAY SCREEN & ACTIONS
# ==========================================

@app.route("/dungeon/<int:dungeon_id>/play")
def dungeon_play(dungeon_id: int):
    """Primary dungeon exploration view."""
    dungeon = db.get_dungeon(dungeon_id)
    if not dungeon:
        return redirect(url_for("dungeon_menu"))

    current_room = db.get_room(dungeon.current_room_id) if dungeon.current_room_id else None
    if not current_room:
        rooms = db.get_rooms_for_dungeon(dungeon_id)
        current_room = rooms[-1] if rooms else None

    # Get recent debug roll, tension message, or progress message from query string
    debug_info = request.args.get("debug_info")
    tension_msg = request.args.get("tension_msg")
    progress_msg = request.args.get("progress_msg")

    return render_template(
        "dungeon_play.html",
        dungeon=dungeon,
        room=current_room,
        formatted_time=format_dungeon_time(dungeon.elapsed_minutes),
        debug_info=debug_info,
        tension_msg=tension_msg,
        progress_msg=progress_msg,
    )


@app.route("/dungeon/<int:dungeon_id>/explore", methods=["POST"])
def dungeon_explore(dungeon_id: int):
    """Generates the next room via hidden Explore Progress roll or floor descent."""
    dungeon = db.get_dungeon(dungeon_id)
    if not dungeon or dungeon.is_complete:
        return redirect(url_for("dungeon_play", dungeon_id=dungeon_id))

    current_room = db.get_room(dungeon.current_room_id) if dungeon.current_room_id else None
    if not current_room:
        return redirect(url_for("dungeon_play", dungeon_id=dungeon_id))

    try:
        new_room, progress_result, tension_event, log_msg = engine.explore(dungeon, current_room)
    except ValueError:
        return redirect(url_for("dungeon_play", dungeon_id=dungeon_id))

    # Save new room
    new_room.dungeon_id = dungeon.id
    room_id = db.save_room(new_room)
    new_room.id = room_id

    # Update dungeon state
    dungeon.current_room_id = room_id
    db.update_dungeon(dungeon)

    # Log exploration
    db.add_log_entry(dungeon.id, dungeon.elapsed_minutes, log_msg)

    # Handle tension event logging
    tension_msg = None
    if tension_event and tension_event.get("triggered"):
        ev = tension_event["event"]
        tension_desc = ev.get("description", "")
        tension_title = ev.get("type", "Tension Event")
        tension_msg = f"[Hour {dungeon.elapsed_minutes // 60} Check] {tension_title}: {tension_desc}"
        db.add_log_entry(dungeon.id, dungeon.elapsed_minutes, tension_msg)

    # Handle progress advancement logging
    progress_msg = None
    if progress_result and progress_result.progress_message:
        progress_msg = progress_result.progress_message
        db.add_log_entry(dungeon.id, dungeon.elapsed_minutes, progress_msg)

    # Debug roll info for developers
    debug_info = None
    if progress_result:
        rolls_str = ", ".join(str(r) for r in progress_result.rolls)
        outcome_label = {
            "failure": "Failure (Normal Room, 0 Progress)",
            "weak": "Weak Success (Normal Room, +1 Progress)",
            "strong": "Strong Success (Unique Room Generated!)",
        }.get(progress_result.outcome, progress_result.outcome)
        debug_info = f"Progress Pool: {progress_result.dice_pool}D6 | Roll: [{rolls_str}] | Successes: {progress_result.successes} -> {outcome_label}"

    return redirect(url_for(
        "dungeon_play",
        dungeon_id=dungeon_id,
        debug_info=debug_info if app.config.get("DEBUG_DUNGEON_ROLLS") else None,
        tension_msg=tension_msg,
        progress_msg=progress_msg,
    ))


@app.route("/dungeon/<int:dungeon_id>/search", methods=["POST"])
def dungeon_search(dungeon_id: int):
    """Searches the current chamber (once per room)."""
    dungeon = db.get_dungeon(dungeon_id)
    if not dungeon:
        return redirect(url_for("dungeon_menu"))

    current_room = db.get_room(dungeon.current_room_id)
    if not current_room or current_room.searched:
        return redirect(url_for("dungeon_play", dungeon_id=dungeon_id))

    search_res, tension_event, log_msg = engine.search(dungeon, current_room)

    # Update room & dungeon
    db.save_room(current_room)
    db.update_dungeon(dungeon)

    # Log search
    db.add_log_entry(dungeon.id, dungeon.elapsed_minutes, log_msg)

    # Handle tension event logging
    tension_msg = None
    if tension_event and tension_event.get("triggered"):
        ev = tension_event["event"]
        tension_desc = ev.get("description", "")
        tension_title = ev.get("type", "Tension Event")
        tension_msg = f"[Hour {dungeon.elapsed_minutes // 60} Check] {tension_title}: {tension_desc}"
        db.add_log_entry(dungeon.id, dungeon.elapsed_minutes, tension_msg)

    return redirect(url_for(
        "dungeon_play",
        dungeon_id=dungeon_id,
        tension_msg=tension_msg,
    ))


@app.route("/dungeon/<int:dungeon_id>/reveal-trap", methods=["POST"])
def dungeon_reveal_trap(dungeon_id: int):
    """Reveals an unidentified trap in the current chamber."""
    dungeon = db.get_dungeon(dungeon_id)
    if not dungeon:
        return redirect(url_for("dungeon_menu"))

    current_room = db.get_room(dungeon.current_room_id) if dungeon.current_room_id else None
    if not current_room or not current_room.has_trap:
        return redirect(url_for("dungeon_play", dungeon_id=dungeon_id))

    if not current_room.trap_revealed:
        trap_data, log_msg = engine.reveal_trap(current_room)
        db.save_room(current_room)
        db.add_log_entry(dungeon.id, dungeon.elapsed_minutes, log_msg)

    return redirect(url_for("dungeon_play", dungeon_id=dungeon_id))


@app.route("/dungeon/<int:dungeon_id>/delete", methods=["POST"])
def dungeon_delete(dungeon_id: int):
    """Deletes a dungeon save."""
    db.delete_dungeon(dungeon_id)
    return redirect(url_for("dungeon_menu"))


# ==========================================
# DUNGEON LOG & EXPORT
# ==========================================

@app.route("/dungeon/<int:dungeon_id>/log")
def dungeon_log_api(dungeon_id: int):
    """Returns JSON log entries for modal display."""
    dungeon = db.get_dungeon(dungeon_id)
    if not dungeon:
        return jsonify({"error": "Dungeon not found"}), 404
    logs = db.get_dungeon_logs(dungeon_id)
    return jsonify({
        "dungeon_name": dungeon.name,
        "logs": logs,
    })


@app.route("/dungeon/<int:dungeon_id>/export")
def dungeon_export(dungeon_id: int):
    """Export the dungeon log as Plain Text (.txt) or Markdown (.md for Obsidian)."""
    dungeon = db.get_dungeon(dungeon_id)
    if not dungeon:
        return redirect(url_for("dungeon_menu"))

    export_format = request.args.get("format", "md").lower()
    logs = db.get_dungeon_logs(dungeon_id)

    if export_format == "txt":
        lines = [
            f"{dungeon.name.upper()} — LOG",
            f"Type: {dungeon.dungeon_type} | Level: {dungeon.current_level} | Time: {format_dungeon_time(dungeon.elapsed_minutes)}",
            "-" * 40,
        ]
        for entry in logs:
            lines.append(f"{entry['formatted_time']} — {entry['entry']}")
        content = "\n".join(lines)
        return Response(
            content,
            mimetype="text/plain",
            headers={"Content-Disposition": f'attachment; filename="{dungeon.name}_log.txt"'},
        )

    # Markdown export (Obsidian friendly)
    md_lines = [
        f"# {dungeon.name}",
        f"**Type:** {dungeon.dungeon_type} | **Level:** {dungeon.current_level} | **Time Explored:** {format_dungeon_time(dungeon.elapsed_minutes)}",
        "",
        "## Exploration Log",
        "",
    ]
    for entry in logs:
        md_lines.append(f"- **{entry['formatted_time']}** — {entry['entry']}")

    md_content = "\n".join(md_lines) + "\n"
    return Response(
        md_content,
        mimetype="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{dungeon.name}_log.md"'},
    )


# ==========================================
# CHARACTER EMULATOR ROUTES
# ==========================================

@app.route("/emulator")
def emulator_main():
    """Character Emulator main screen."""
    all_current = db.list_npcs(current_only=True)
    party_members = [npc for npc in all_current if npc["party_member"]]
    current_npcs = [npc for npc in all_current if not npc["party_member"]]

    # Sort alphabetically by name (case-insensitive)
    party_members.sort(key=lambda x: x["name"].lower())
    current_npcs.sort(key=lambda x: x["name"].lower())

    return render_template(
        "emulator.html",
        party_members=party_members,
        current_npcs=current_npcs,
        action_tables=emulator.ACTION_TABLE_NAMES,
        spark_tables=emulator.SPARK_TABLE_NAMES,
        spark_combos=list(emulator.SPARK_COMBINATIONS.keys()),
    )


@app.route("/emulator/npc/new", methods=["POST"])
def emulator_npc_new():
    """Create a new NPC."""
    if request.is_json:
        data = request.get_json() or {}
        name = data.get("name", "").strip()
        details = data.get("details", "").strip()
        current = bool(data.get("current", True))
        party_member = bool(data.get("party_member", False))
        traits = data.get("traits", [])
    else:
        name = request.form.get("name", "").strip()
        details = request.form.get("details", "").strip()
        current = bool(request.form.get("current", True))
        party_member = bool(request.form.get("party_member", False))
        traits = []

    if not name:
        if request.is_json:
            return jsonify({"success": False, "error": "NPC name cannot be empty."}), 400
        return redirect(url_for("emulator_main"))

    try:
        npc_id = db.create_npc(
            name=name,
            details=details,
            current=current,
            party_member=party_member,
            traits=traits,
        )
    except ValueError as e:
        if request.is_json:
            return jsonify({"success": False, "error": str(e)}), 400
        return redirect(url_for("emulator_main"))

    if request.is_json:
        npc = db.get_npc(npc_id)
        return jsonify({"success": True, "npc": npc})

    return redirect(url_for("emulator_main"))


@app.route("/emulator/npc/<int:npc_id>/toggle-status", methods=["POST"])
def emulator_npc_toggle_status(npc_id: int):
    """Toggle Current or Party Member status for an NPC with validation."""
    npc = db.get_npc(npc_id)
    if not npc:
        return jsonify({"success": False, "error": "NPC not found."}), 404

    data = request.get_json() or {}
    new_current = data.get("current")
    new_party_member = data.get("party_member")

    try:
        db.update_npc(
            npc_id=npc_id,
            current=new_current,
            party_member=new_party_member,
        )
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400

    updated = db.get_npc(npc_id)
    return jsonify({"success": True, "npc": updated})


@app.route("/emulator/npc/<int:npc_id>/edit", methods=["POST"])
def emulator_npc_edit(npc_id: int):
    """Full edit for an NPC."""
    npc = db.get_npc(npc_id)
    if not npc:
        if request.is_json:
            return jsonify({"success": False, "error": "NPC not found."}), 404
        return redirect(url_for("emulator_main"))

    if request.is_json:
        data = request.get_json() or {}
        name = data.get("name", "").strip()
        details = data.get("details", "").strip()
        current = data.get("current")
        party_member = data.get("party_member")
        traits = data.get("traits")
    else:
        name = request.form.get("name", "").strip()
        details = request.form.get("details", "").strip()
        current = bool(request.form.get("current"))
        party_member = bool(request.form.get("party_member"))
        traits = None

    try:
        db.update_npc(
            npc_id=npc_id,
            name=name if name else None,
            details=details,
            current=current,
            party_member=party_member,
        )
        if traits is not None:
            db.set_npc_traits(npc_id, traits)
    except ValueError as e:
        if request.is_json:
            return jsonify({"success": False, "error": str(e)}), 400
        return redirect(url_for("emulator_main"))

    updated = db.get_npc(npc_id)
    if request.is_json:
        return jsonify({"success": True, "npc": updated})
    return redirect(url_for("emulator_main"))


@app.route("/emulator/npc/<int:npc_id>/delete", methods=["POST"])
def emulator_npc_delete(npc_id: int):
    """Permanently delete an NPC and associated traits."""
    deleted = db.delete_npc(npc_id)
    if not deleted:
        if request.is_json:
            return jsonify({"success": False, "error": "NPC not found."}), 404
        return redirect(url_for("emulator_main"))

    if request.is_json:
        return jsonify({"success": True, "npc_id": npc_id})
    return redirect(url_for("emulator_main"))


@app.route("/emulator/npc/<int:npc_id>/traits/add", methods=["POST"])
def emulator_npc_add_trait(npc_id: int):
    """Quick Add Trait to an NPC."""
    npc = db.get_npc(npc_id)
    if not npc:
        return jsonify({"success": False, "error": "NPC not found."}), 404

    data = request.get_json() or {}
    status = data.get("status", "default").strip().lower()
    trait = data.get("trait", "").strip()
    category = data.get("category", "PR").strip().upper()

    if not trait:
        return jsonify({"success": False, "error": "Trait text cannot be empty."}), 400

    try:
        trait_id = db.add_npc_trait(npc_id, status, trait, category)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400

    updated = db.get_npc(npc_id)
    return jsonify({
        "success": True,
        "trait": {
            "id": trait_id,
            "status": status.capitalize(),
            "trait": trait,
            "category": category,
        },
        "npc": updated,
    })


@app.route("/emulator/npc/<int:npc_id>/traits/<int:trait_id>/delete", methods=["POST"])
def emulator_npc_delete_trait(npc_id: int, trait_id: int):
    """Delete a trait from an NPC."""
    deleted = db.delete_npc_trait(trait_id)
    if not deleted:
        return jsonify({"success": False, "error": "Trait not found."}), 404
    updated = db.get_npc(npc_id)
    return jsonify({"success": True, "npc": updated})


@app.route("/emulator/npc/<int:npc_id>/roll-action", methods=["POST"])
def emulator_npc_roll_action(npc_id: int):
    """Roll 3 independent behavioral action prompts for an NPC."""
    npc = db.get_npc(npc_id)
    if not npc:
        return jsonify({"success": False, "error": "NPC not found."}), 404

    data = request.get_json() or {}
    action_type = data.get("action_type", "downtime").strip().lower()

    try:
        results = emulator.roll_specific_action(action_type, npc["traits"])
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400

    return jsonify({
        "success": True,
        "npc_id": npc_id,
        "action_type": action_type.capitalize(),
        "results": results,
    })


@app.route("/emulator/npc/<int:npc_id>/roll-spark", methods=["POST"])
def emulator_npc_roll_spark(npc_id: int):
    """Roll a Spark table or combination for an NPC."""
    npc = db.get_npc(npc_id)
    if not npc:
        return jsonify({"success": False, "error": "NPC not found."}), 404

    data = request.get_json() or {}
    spark_type = data.get("spark_type", "method").strip().lower()

    try:
        spark_result = emulator.roll_spark(spark_type)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400

    return jsonify({
        "success": True,
        "npc_id": npc_id,
        "spark": spark_result,
    })


@app.route("/emulator/api/npcs", methods=["GET"])
def emulator_api_list_npcs():
    """List or search all stored NPCs for Find NPC and Manage NPCs."""
    query = request.args.get("q", "").strip()
    npcs = db.list_npcs(search_query=query if query else None)
    return jsonify({"success": True, "npcs": npcs})


@app.route("/emulator/npc/<int:npc_id>/make-current", methods=["POST"])
def emulator_npc_make_current(npc_id: int):
    """Set NPC current = True."""
    npc = db.get_npc(npc_id)
    if not npc:
        return jsonify({"success": False, "error": "NPC not found."}), 404
    db.update_npc(npc_id, current=True)
    updated = db.get_npc(npc_id)
    return jsonify({"success": True, "npc": updated})


@app.route("/emulator/npc/<int:npc_id>/remove-current", methods=["POST"])
def emulator_npc_remove_current(npc_id: int):
    """Remove NPC from current scene (current = False) without deleting."""
    npc = db.get_npc(npc_id)
    if not npc:
        return jsonify({"success": False, "error": "NPC not found."}), 404

    try:
        db.update_npc(npc_id, current=False)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400

    updated = db.get_npc(npc_id)
    return jsonify({"success": True, "npc": updated})


if __name__ == "__main__":
    app.run(host=app.config["HOST"], port=app.config["PORT"], debug=app.config["DEBUG"])

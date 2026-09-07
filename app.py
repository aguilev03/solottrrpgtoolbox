"""Solo TTRPG Tools - Flask Application."""

import os
from flask import Flask, Response, jsonify, redirect, render_template, request, url_for
from config import Config
from database import get_db
from dungeon_engine import DungeonEngine, DungeonState, format_dungeon_time
from table_loader import get_table_manager

app = Flask(__name__)
app.config.from_object(Config)

# Initialize database and table manager
db = get_db(app.config["DATABASE_PATH"])
table_manager = get_table_manager(app.config["DATA_DIR"])
engine = DungeonEngine(table_manager)


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


if __name__ == "__main__":
    app.run(host=app.config["HOST"], port=app.config["PORT"], debug=app.config["DEBUG"])

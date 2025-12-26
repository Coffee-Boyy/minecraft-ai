package me.coffeeboy;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

public class Protocol {
    private static final Gson GSON = new Gson();

    /**
     * Human-readable action schema snippet included in the system prompt.
     * Mirrors the Python agent's ACTION_SCHEMA_DESCRIPTION.
     */
    public static final String ACTION_SCHEMA_DESCRIPTION = """
        {
          "forward": float (-1.0 to 1.0, negative=backward),
          "strafe": float (-1.0 to 1.0, negative=left, positive=right),
          "yaw": float (absolute yaw in degrees, 0=south, 90=west, 180=north, -90=east),
          "pitch": float (absolute pitch in degrees, -90=up, 0=straight, 90=down),
          "jump": bool,
          "attack": bool (left click),
          "use": bool (right click),
          "sneak": bool,
          "sprint": bool,
          "duration_ms": int (20-2000, how long to hold this action)
        }""";

    /**
     * Formal schema used for OpenAI-compatible "structured outputs" via:
     * response_format: { type: "json_schema", json_schema: ACTION_JSON_SCHEMA }
     *
     * Mirrors the Python agent's ACTION_JSON_SCHEMA.
     */
    public static final JsonObject ACTION_JSON_SCHEMA = JsonParser.parseString("""
        {
          "name": "minecraft_action",
          "strict": true,
          "schema": {
            "type": "object",
            "properties": {
              "forward": {
                "type": "number",
                "description": "Movement forward/backward (-1.0 to 1.0, negative=backward)"
              },
              "strafe": {
                "type": "number",
                "description": "Movement left/right (-1.0 to 1.0, negative=left, positive=right)"
              },
              "yaw": {
                "type": "number",
                "description": "Absolute yaw in degrees (0=south, 90=west, 180=north, -90=east)"
              },
              "pitch": {
                "type": "number",
                "description": "Absolute pitch in degrees (-90=up, 0=straight, 90=down)"
              },
              "jump": { "type": "boolean", "description": "Whether to jump" },
              "attack": { "type": "boolean", "description": "Left click (break blocks or hit entities)" },
              "use": { "type": "boolean", "description": "Right click (place blocks or interact)" },
              "sneak": { "type": "boolean", "description": "Whether to sneak" },
              "sprint": { "type": "boolean", "description": "Whether to sprint" },
              "duration_ms": {
                "type": "integer",
                "description": "How long to hold this action (20-2000ms)"
              }
            },
            "required": [
              "forward",
              "strafe",
              "yaw",
              "pitch",
              "jump",
              "attack",
              "use",
              "sneak",
              "sprint",
              "duration_ms"
            ],
            "additionalProperties": false
          }
        }
        """).getAsJsonObject();

    // Action types
    public static final String ACTION_MOVE = "move";
    public static final String ACTION_LOOK = "look";
    public static final String ACTION_JUMP = "jump";
    public static final String ACTION_ATTACK = "attack";
    public static final String ACTION_USE = "use";
    public static final String ACTION_SNEAK = "sneak";
    public static final String ACTION_SPRINT = "sprint";

    // Message types
    public static class ActionMessage {
        public String type;
        public float forward;      // -1.0 to 1.0
        public float strafe;       // -1.0 to 1.0
        public float yaw;          // degrees
        public float pitch;        // degrees
        public boolean jump;
        public boolean attack;
        public boolean use;
        public boolean sneak;
        public boolean sprint;
        public int duration_ms;    // duration in milliseconds

        public static ActionMessage fromJson(String json) {
            return GSON.fromJson(json, ActionMessage.class);
        }

        public String toJson() {
            return GSON.toJson(this);
        }
    }

    public static class StateMessage {
        public String type = "state";
        public PlayerState player;
        public WorldState world;

        public String toJson() {
            return GSON.toJson(this);
        }
    }

    public static class PlayerState {
        public double x, y, z;
        public float yaw, pitch;
        public float health;
        public float food;
        public int experience_level;
        public boolean on_ground;
        public boolean in_water;
        public boolean in_lava;
    }

    public static class WorldState {
        public String dimension;
        public long time;
        public boolean is_raining;
        public boolean is_thundering;
    }

    public static class AckMessage {
        public String type = "ack";
        public String action_type;
        public boolean success;
        public String error;

        public String toJson() {
            return GSON.toJson(this);
        }
    }

    /**
     * Configuration message for frame capture settings.
     * Received from Python client to configure capture parameters.
     */
    public static class FrameConfigMessage {
        public String type = "frame_config";
        public boolean enabled = true;
        public int width = 854;
        public int height = 480;
        public int captureEveryNFrames = 1;  // 1 = every frame, 2 = every other, etc.
        public float jpegQuality = 0.75f;    // 0.0 to 1.0

        public static FrameConfigMessage fromJson(String json) {
            return GSON.fromJson(json, FrameConfigMessage.class);
        }

        public String toJson() {
            return GSON.toJson(this);
        }
    }
}

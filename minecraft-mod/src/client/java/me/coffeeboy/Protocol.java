package me.coffeeboy;

import com.google.gson.Gson;

public class Protocol {
    private static final Gson GSON = new Gson();

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

package me.coffeeboy;

import com.google.gson.Gson;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Base64;

import static me.coffeeboy.Protocol.ACTION_SCHEMA_DESCRIPTION;
import static me.coffeeboy.Protocol.ACTION_JSON_SCHEMA;

/**
 * Minimal OpenAI-compatible chat/completions client.
 *
 * Sends a JPEG frame as a data URL and asks the model for a JSON action.
 */
public final class LLMClient {
    private static final Gson GSON = new Gson();

    private final HttpClient http;
    private final AgentConfig config;

    public LLMClient(AgentConfig config) {
        this.config = config;
        this.http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();
    }

    public Protocol.ActionMessage requestAction(byte[] jpegBytes, String goal, Protocol.StateMessage state) throws Exception {
        String imageDataUrl = "data:image/jpeg;base64," + Base64.getEncoder().encodeToString(jpegBytes);

        JsonObject payload = new JsonObject();
        payload.addProperty("model", config.llmModel);
        payload.add("messages", buildMessages(goal, state, imageDataUrl));
        payload.addProperty("max_tokens", config.maxTokens);
        payload.addProperty("temperature", 0.0);
        payload.addProperty("top_p", 1.0);
        payload.addProperty("top_k", 0);
        payload.addProperty("frequency_penalty", 1.1);

        // Structured outputs (best-effort): ask the server to validate/enforce the action schema.
        // Mirrors the Python agent's request payload.
        JsonObject responseFormat = new JsonObject();
        responseFormat.addProperty("type", "json_schema");
        responseFormat.add("json_schema", ACTION_JSON_SCHEMA);
        payload.add("response_format", responseFormat);

        String body = GSON.toJson(payload);
        URI uri = URI.create(config.llmBaseUrl + "/chat/completions");

        HttpRequest req = HttpRequest.newBuilder()
            .uri(uri)
            .timeout(Duration.ofSeconds(60))
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8))
            .build();

        HttpResponse<String> resp = http.send(req, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        if (resp.statusCode() < 200 || resp.statusCode() >= 300) {
            throw new RuntimeException("LLM HTTP " + resp.statusCode() + ": " + truncate(resp.body(), 500));
        }

        return parseActionFromChatCompletions(resp.body());
    }

    private static JsonElement buildMessages(String goal, Protocol.StateMessage state, String imageDataUrl) {
        JsonObject system = new JsonObject();
        system.addProperty("role", "system");
        system.addProperty("content",
            "You are a Minecraft control policy. Given a screenshot of the current Minecraft world and goal, output ONLY a JSON action." +
                "Action schema:\n" +
                ACTION_SCHEMA_DESCRIPTION +

                "Rules:\n" +
                "- Output ONLY valid JSON, no explanation or markdown\n" +
                "- Keep actions short (100-300ms duration) for responsive control\n" +
                "- Use forward=1.0 to walk forward, strafe for sideways movement\n" +
                "- Set jump=true to jump, sprint=true to run faster\n" +
                "- Use attack=true to break blocks or hit entities\n" +
                "- Use use=true to place blocks or interact");

        JsonObject user = new JsonObject();
        user.addProperty("role", "user");

        // Multi-part content: text + image_url (OpenAI vision style).
        com.google.gson.JsonArray parts = new com.google.gson.JsonArray();

        JsonObject textPart = new JsonObject();
        textPart.addProperty("type", "text");
        StringBuilder txt = new StringBuilder();
        txt.append("Goal: ").append(goal);
        if (state != null && state.player != null && state.world != null) {
            txt.append("\nState: ")
                .append("{")
                // .append("\"pos\":[").append(state.player.x).append(",").append(state.player.y).append(",").append(state.player.z).append("],")
                .append("\"health\":").append(state.player.health).append(",")
                .append("\"hunger\":").append(state.player.food)
                .append("}");
        }
        textPart.addProperty("text", txt.toString());
        parts.add(textPart);

        JsonObject imagePart = new JsonObject();
        imagePart.addProperty("type", "image_url");
        JsonObject imageUrl = new JsonObject();
        imageUrl.addProperty("url", imageDataUrl);
        imagePart.add("image_url", imageUrl);
        parts.add(imagePart);

        user.add("content", parts);

        com.google.gson.JsonArray messages = new com.google.gson.JsonArray();
        messages.add(system);
        messages.add(user);
        return messages;
    }

    private static Protocol.ActionMessage parseActionFromChatCompletions(String json) {
        JsonObject root = JsonParser.parseString(json).getAsJsonObject();
        JsonObject choice0 = root.getAsJsonArray("choices").get(0).getAsJsonObject();
        JsonObject msg = choice0.getAsJsonObject("message");
        String content = msg.get("content").getAsString().trim();

        // Content should be JSON. Some models wrap with code fences; strip if needed.
        if (content.startsWith("```")) {
            String[] lines = content.split("\n");
            StringBuilder sb = new StringBuilder();
            for (String line : lines) {
                if (line.startsWith("```")) continue;
                sb.append(line).append("\n");
            }
            content = sb.toString().trim();
        }

        JsonObject actionObj = JsonParser.parseString(content).getAsJsonObject();
        Protocol.ActionMessage action = new Protocol.ActionMessage();
        action.type = "action";
        action.forward = getFloat(actionObj, "forward", 0f);
        action.strafe = getFloat(actionObj, "strafe", 0f);
        action.yaw = getFloat(actionObj, "yaw", 0f);
        action.pitch = getFloat(actionObj, "pitch", 0f);
        action.jump = getBool(actionObj, "jump", false);
        action.attack = getBool(actionObj, "attack", false);
        action.use = getBool(actionObj, "use", false);
        action.sneak = getBool(actionObj, "sneak", false);
        action.sprint = getBool(actionObj, "sprint", false);
        action.duration_ms = clampInt(getInt(actionObj, "duration_ms", 150), 20, 2000);
        return action;
    }

    private static float getFloat(JsonObject obj, String key, float def) {
        try {
            if (!obj.has(key) || obj.get(key).isJsonNull()) return def;
            return obj.get(key).getAsFloat();
        } catch (Exception ignored) {
            return def;
        }
    }

    private static int getInt(JsonObject obj, String key, int def) {
        try {
            if (!obj.has(key) || obj.get(key).isJsonNull()) return def;
            return obj.get(key).getAsInt();
        } catch (Exception ignored) {
            return def;
        }
    }

    private static boolean getBool(JsonObject obj, String key, boolean def) {
        try {
            if (!obj.has(key) || obj.get(key).isJsonNull()) return def;
            return obj.get(key).getAsBoolean();
        } catch (Exception ignored) {
            return def;
        }
    }

    private static String truncate(String s, int max) {
        if (s == null) return "";
        if (s.length() <= max) return s;
        return s.substring(0, max) + "...";
    }

    private static int clampInt(int v, int lo, int hi) {
        return Math.max(lo, Math.min(hi, v));
    }
}



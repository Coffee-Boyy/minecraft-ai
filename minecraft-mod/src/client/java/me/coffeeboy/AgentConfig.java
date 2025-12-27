package me.coffeeboy;

/**
 * Simple config for running the agent inside the mod.
 *
 * For now this reads JVM system properties so it's easy to tweak in dev runs.
 * Example (Gradle runClient):
 *   -Dminecraftai.llmBaseUrl=http://127.0.0.1:7000/v1
 *   -Dminecraftai.llmModel=Qwen/Qwen2-VL-2B-Instruct
 *   -Dminecraftai.llmLogEnabled=1
 *   -Dminecraftai.llmLogFile=llm_api.log
 */
public final class AgentConfig {
    public final String llmBaseUrl;
    public final String llmModel;
    public final int maxTokens;
    public final int decisionHz;
    public final String goal;

    public final int captureWidth;
    public final int captureHeight;
    public final int captureEveryNFrames;
    public final float jpegQuality;

    public final boolean debugSaveFrames;
    public final int debugSaveEveryNFrames;
    /**
     * Directory where debug frames will be written.
     * If relative, it's resolved against the Minecraft game dir.
     */
    public final String debugFramesDir;

    /**
     * If enabled, writes full LLM HTTP request/response bodies to {@link #llmLogFile}.
     * WARNING: requests include base64-encoded image data and can get very large.
     */
    public final boolean llmLogEnabled;
    /**
     * File path for LLM request/response logging.
     * If relative, it's resolved against the Minecraft game dir.
     */
    public final String llmLogFile;

    private AgentConfig(
        String llmBaseUrl,
        String llmModel,
        int maxTokens,
        int decisionHz,
        String goal,
        int captureWidth,
        int captureHeight,
        int captureEveryNFrames,
        float jpegQuality,
        boolean debugSaveFrames,
        int debugSaveEveryNFrames,
        String debugFramesDir,
        boolean llmLogEnabled,
        String llmLogFile
    ) {
        this.llmBaseUrl = llmBaseUrl;
        this.llmModel = llmModel;
        this.maxTokens = maxTokens;
        this.decisionHz = decisionHz;
        this.goal = goal;
        this.captureWidth = captureWidth;
        this.captureHeight = captureHeight;
        this.captureEveryNFrames = captureEveryNFrames;
        this.jpegQuality = jpegQuality;
        this.debugSaveFrames = debugSaveFrames;
        this.debugSaveEveryNFrames = debugSaveEveryNFrames;
        this.debugFramesDir = debugFramesDir;
        this.llmLogEnabled = llmLogEnabled;
        this.llmLogFile = llmLogFile;
    }

    public static AgentConfig fromSystemProperties() {
        String baseUrl = System.getProperty("minecraftai.llmBaseUrl", "http://127.0.0.1:7000/v1");
        String model = System.getProperty("minecraftai.llmModel", "Qwen/Qwen2-VL-2B-Instruct");
        int maxTokens = parseInt(System.getProperty("minecraftai.maxTokens", "128"), 128);
        int decisionHz = parseInt(System.getProperty("minecraftai.decisionHz", "6"), 6);
        String goal = System.getProperty("minecraftai.goal", "explore and survive");

        int width = parseInt(System.getProperty("minecraftai.captureWidth", "384"), 384);
        int height = parseInt(System.getProperty("minecraftai.captureHeight", "216"), 216);
        int everyN = parseInt(System.getProperty("minecraftai.captureEveryNFrames", "6"), 6);
        float quality = parseFloat(System.getProperty("minecraftai.jpegQuality", "0.5"), 0.5f);

        boolean debugSaveFrames = parseBool(System.getProperty("minecraftai.debugSaveFrames", "1"), true);
        int debugEveryNFrames = parseInt(System.getProperty("minecraftai.debugSaveEveryNFrames", "30"), 30);
        String debugFramesDir = System.getProperty("minecraftai.debugFramesDir", "mcagent_frames");

        boolean llmLogEnabled = parseBool(System.getProperty("minecraftai.llmLogEnabled", "0"), false);
        String llmLogFile = System.getProperty("minecraftai.llmLogFile", "llm_api.log");

        return new AgentConfig(
            baseUrl, model, maxTokens, decisionHz, goal,
            width, height, everyN, quality,
            debugSaveFrames, debugEveryNFrames, debugFramesDir,
            llmLogEnabled, llmLogFile
        );
    }

    private static int parseInt(String s, int fallback) {
        try {
            return Integer.parseInt(s);
        } catch (Exception ignored) {
            return fallback;
        }
    }

    private static float parseFloat(String s, float fallback) {
        try {
            return Float.parseFloat(s);
        } catch (Exception ignored) {
            return fallback;
        }
    }

    private static boolean parseBool(String s, boolean fallback) {
        try {
            if (s == null) return fallback;
            String v = s.trim().toLowerCase();
            return v.equals("1") || v.equals("true") || v.equals("yes") || v.equals("y");
        } catch (Exception ignored) {
            return fallback;
        }
    }
}



package me.coffeeboy;

import net.minecraft.client.Minecraft;

import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Runs the "agent" inside the Minecraft client:
 * - receives JPEG frames from FrameCapture
 * - calls LLM over HTTP off-thread
 * - applies the returned action on the client thread via ActionApplier
 */
public final class AgentController {
    private final Minecraft minecraft;
    private final ActionApplier actionApplier;
    private final FrameCapture frameCapture;
    private final AgentConfig config;
    private final LLMClient llm;

    private final ExecutorService worker;
    private final AtomicBoolean inferenceInFlight = new AtomicBoolean(false);
    private volatile long lastDecisionMs = 0;
    private volatile boolean enabled = true;

    private int framesSeen = 0;
    private final DebugFrameBuffer debugFrames;

    // Metrics (simple, thread-safe)
    private final AtomicLong decisions = new AtomicLong(0);
    private final AtomicLong actionsEnqueued = new AtomicLong(0);
    private final AtomicLong acksReceived = new AtomicLong(0);
    private final AtomicLong errors = new AtomicLong(0);
    private final AtomicLong totalCaptureMs = new AtomicLong(0);
    private final AtomicLong totalEncodeMs = new AtomicLong(0);
    private final AtomicLong totalInferenceMs = new AtomicLong(0);
    private final AtomicLong totalTotalMs = new AtomicLong(0);

    private volatile double lastInferenceMs = 0.0;
    private volatile String lastActionSummary = "";

    public AgentController(Minecraft minecraft, ActionApplier actionApplier, FrameCapture frameCapture, AgentConfig config) {
        this.minecraft = minecraft;
        this.actionApplier = actionApplier;
        this.frameCapture = frameCapture;
        this.config = config;
        this.llm = new LLMClient(config);
        this.debugFrames = new DebugFrameBuffer(5, config.debugFramesDir);
        this.worker = Executors.newSingleThreadExecutor(new ThreadFactory() {
            @Override
            public Thread newThread(Runnable r) {
                Thread t = new Thread(r, "MinecraftAI-Agent");
                t.setDaemon(true);
                return t;
            }
        });
    }

    public void start() {
        // Configure capture directly (no websocket frame_config).
        frameCapture.setResolution(config.captureWidth, config.captureHeight);
        frameCapture.setCaptureRate(config.captureEveryNFrames);
        frameCapture.setJpegQuality(config.jpegQuality);
        frameCapture.setEnabled(true);

        frameCapture.setFrameCallback(this::onFrame);

        MinecraftAI.LOGGER.info(
            "In-mod agent enabled. LLM={} model={} decisionHz={} capture={}x{} everyN={} jpegQ={}",
            config.llmBaseUrl, config.llmModel, config.decisionHz,
            config.captureWidth, config.captureHeight, config.captureEveryNFrames, config.jpegQuality
        );
    }

    public void stop() {
        enabled = false;
        frameCapture.setEnabled(false);
        worker.shutdownNow();
    }

    public AgentStatsSnapshot getStatsSnapshot() {
        long iters = Math.max(1, decisions.get());
        return new AgentStatsSnapshot(
            framesSeen,
            decisions.get(),
            actionsEnqueued.get(),
            acksReceived.get(),
            errors.get(),
            totalCaptureMs.get() / (double) iters,
            totalEncodeMs.get() / (double) iters,
            totalInferenceMs.get() / (double) iters,
            totalTotalMs.get() / (double) iters,
            lastInferenceMs,
            lastActionSummary
        );
    }

    private void onFrame(byte[] jpegBytes) {
        if (!enabled) return;

        framesSeen++;
        if (config.debugSaveFrames) {
            debugFrames.addFrame(jpegBytes);
            if (framesSeen <= 5 || (config.debugSaveEveryNFrames > 0 && framesSeen % config.debugSaveEveryNFrames == 0)) {
                debugFrames.writeToDiskBestEffort();
            }
        }
        if (framesSeen <= 3 || framesSeen % 120 == 0) {
            MinecraftAI.LOGGER.info("AgentController saw frame {} ({} bytes)", framesSeen, jpegBytes.length);
        }

        // Only run the agent in-world (prevents wasting LLM calls in menus/loading).
        if (minecraft.player == null || minecraft.level == null) {
            return;
        }

        long now = System.currentTimeMillis();
        long minIntervalMs = Math.max(1, 1000L / Math.max(1, config.decisionHz));
        if (now - lastDecisionMs < minIntervalMs) {
            return; // throttle
        }

        if (!inferenceInFlight.compareAndSet(false, true)) {
            return; // drop if we're already doing inference
        }

        // Snapshot state on client thread (we're likely on render thread already, but be explicit)
        Protocol.StateMessage state = actionApplier.getState();
        String goal = config.goal;

        lastDecisionMs = now;
        decisions.incrementAndGet();

        // Capture/encode timings are measured in FrameCapture (best-effort).
        totalCaptureMs.addAndGet((long) frameCapture.getLastCaptureMs());
        totalEncodeMs.addAndGet((long) frameCapture.getLastEncodeMs());

        worker.submit(() -> {
            long t0 = System.nanoTime();
            try {
                Protocol.ActionMessage action = llm.requestAction(jpegBytes, goal, state);
                long t1 = System.nanoTime();
                double inferenceMs = (t1 - t0) / 1_000_000.0;
                lastInferenceMs = inferenceMs;
                totalInferenceMs.addAndGet((long) inferenceMs);

                lastActionSummary = String.format(
                    "fwd=%.2f str=%.2f yaw=%.1f pitch=%.1f jump=%s atk=%s use=%s sneak=%s sprint=%s dur=%d",
                    action.forward, action.strafe, action.yaw, action.pitch,
                    action.jump, action.attack, action.use, action.sneak, action.sprint, action.duration_ms
                );

                // Apply on Minecraft client thread
                minecraft.execute(() -> {
                    try {
                        actionsEnqueued.incrementAndGet();
                        actionApplier.applyAction(action, ack -> {
                            acksReceived.incrementAndGet();
                            if (!ack.success) {
                                MinecraftAI.LOGGER.warn("Action failed: type={} error={}", ack.action_type, ack.error);
                                errors.incrementAndGet();
                            }
                        });
                    } catch (Exception e) {
                        MinecraftAI.LOGGER.error("Failed to apply action: {}", e.getMessage());
                        errors.incrementAndGet();
                    }
                });

                if (framesSeen <= 3 || framesSeen % 120 == 0) {
                    MinecraftAI.LOGGER.info("LLM inference took {} ms; action={}", String.format("%.1f", inferenceMs), lastActionSummary);
                }
            } catch (Exception e) {
                MinecraftAI.LOGGER.error("LLM request failed: {}", e.getMessage());
                errors.incrementAndGet();
            } finally {
                totalTotalMs.addAndGet((long) ((System.nanoTime() - t0) / 1_000_000.0));
                inferenceInFlight.set(false);
            }
        });
    }

    public static final class AgentStatsSnapshot {
        public final int framesSeen;
        public final long decisions;
        public final long actionsEnqueued;
        public final long acksReceived;
        public final long errors;
        public final double avgCaptureMs;
        public final double avgEncodeMs;
        public final double avgInferenceMs;
        public final double avgTotalMs;
        public final double lastInferenceMs;
        public final String lastActionSummary;

        public AgentStatsSnapshot(
            int framesSeen,
            long decisions,
            long actionsEnqueued,
            long acksReceived,
            long errors,
            double avgCaptureMs,
            double avgEncodeMs,
            double avgInferenceMs,
            double avgTotalMs,
            double lastInferenceMs,
            String lastActionSummary
        ) {
            this.framesSeen = framesSeen;
            this.decisions = decisions;
            this.actionsEnqueued = actionsEnqueued;
            this.acksReceived = acksReceived;
            this.errors = errors;
            this.avgCaptureMs = avgCaptureMs;
            this.avgEncodeMs = avgEncodeMs;
            this.avgInferenceMs = avgInferenceMs;
            this.avgTotalMs = avgTotalMs;
            this.lastInferenceMs = lastInferenceMs;
            this.lastActionSummary = lastActionSummary;
        }
    }
}



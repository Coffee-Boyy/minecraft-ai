package me.coffeeboy;

import net.fabricmc.fabric.api.client.rendering.v1.HudRenderCallback;
import net.minecraft.client.DeltaTracker;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.Font;
import net.minecraft.client.gui.GuiGraphics;

/**
 * Simple on-screen stats overlay, similar to the Python agent's table.
 */
public final class AgentHud implements HudRenderCallback {
    private final Minecraft mc;
    private final AgentController controller;

    public AgentHud(Minecraft mc, AgentController controller) {
        this.mc = mc;
        this.controller = controller;
    }

    @Override
    public void onHudRender(GuiGraphics graphics, DeltaTracker deltaTracker) {
        if (controller == null) return;

        AgentController.AgentStatsSnapshot s = controller.getStatsSnapshot();
        Font font = mc.font;

        int x = 8;
        int y = 8;
        int line = 10;

        double effectiveHz = s.avgTotalMs > 0 ? (1000.0 / s.avgTotalMs) : 0.0;

        graphics.drawString(font, "MinecraftAI (in-mod)", x, y, 0xFFFFFF, true);
        y += line + 2;

        graphics.drawString(font, "Iterations: " + s.decisions, x, y, 0xA0E7A0, true); y += line;
        graphics.drawString(font, "Frames Seen: " + s.framesSeen, x, y, 0xA0E7A0, true); y += line;
        graphics.drawString(font, "Actions Enqueued: " + s.actionsEnqueued, x, y, 0xA0E7A0, true); y += line;
        graphics.drawString(font, "Acks Received: " + s.acksReceived, x, y, 0xA0E7A0, true); y += line;
        graphics.drawString(font, "Errors: " + s.errors, x, y, 0xFF9090, true); y += line;

        y += 2;
        graphics.drawString(font, String.format("Avg Capture (ms): %.1f", s.avgCaptureMs), x, y, 0xA0C8FF, true); y += line;
        graphics.drawString(font, String.format("Avg Encode (ms): %.1f", s.avgEncodeMs), x, y, 0xA0C8FF, true); y += line;
        graphics.drawString(font, String.format("Avg Inference (ms): %.1f", s.avgInferenceMs), x, y, 0xA0C8FF, true); y += line;
        graphics.drawString(font, String.format("Avg Total (ms): %.1f", s.avgTotalMs), x, y, 0xA0C8FF, true); y += line;
        graphics.drawString(font, String.format("Effective Hz: %.2f", effectiveHz), x, y, 0xA0C8FF, true); y += line;

        if (s.lastActionSummary != null && !s.lastActionSummary.isEmpty()) {
            y += 2;
            graphics.drawString(font, "Last Action:", x, y, 0xFFFFFF, true); y += line;
            graphics.drawString(font, s.lastActionSummary, x, y, 0xFFFFFF, true);
        }
    }
}



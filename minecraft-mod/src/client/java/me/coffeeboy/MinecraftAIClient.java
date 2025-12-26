package me.coffeeboy;

import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.rendering.v1.HudRenderCallback;
import net.minecraft.client.Minecraft;

public class MinecraftAIClient implements ClientModInitializer {
	private static ActionApplier actionApplier;
	private static FrameCapture frameCapture;
	private static AgentController agentController;

	@Override
	public void onInitializeClient() {
		MinecraftAI.LOGGER.info("Initializing Minecraft AI Client");

		// Initialize action applier
		actionApplier = new ActionApplier(Minecraft.getInstance());

		// Initialize frame capture
		frameCapture = new FrameCapture();
		frameCapture.register();
		MinecraftAI.LOGGER.info("Frame capture initialized");

		// Start the in-mod agent controller (HTTP to LLM, no websockets).
		AgentConfig cfg = AgentConfig.fromSystemProperties();
		agentController = new AgentController(Minecraft.getInstance(), actionApplier, frameCapture, cfg);
		agentController.start();

		// HUD overlay with agent-like metrics.
		HudRenderCallback.EVENT.register(new AgentHud(Minecraft.getInstance(), agentController));

		// Register shutdown hook for cleanup
		Runtime.getRuntime().addShutdownHook(new Thread(() -> {
			if (frameCapture != null) {
				frameCapture.shutdown();
			}
		}, "FrameCapture-Shutdown"));

		// Register tick events
		ClientTickEvents.END_CLIENT_TICK.register(client -> {
			if (actionApplier != null) {
				actionApplier.tick();
			}
		});
	}
}
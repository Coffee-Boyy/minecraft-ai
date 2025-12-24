package me.coffeeboy;

import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.minecraft.client.Minecraft;

public class MinecraftAIClient implements ClientModInitializer {
	private static WsServer wsServer;
	private static ActionApplier actionApplier;
	private static FrameCapture frameCapture;

	@Override
	public void onInitializeClient() {
		MinecraftAI.LOGGER.info("Initializing Minecraft AI Client");

		// Initialize action applier
		actionApplier = new ActionApplier(Minecraft.getInstance());

		// Start WebSocket server
		try {
			wsServer = new WsServer(8765, actionApplier);
			wsServer.start();
			MinecraftAI.LOGGER.info("WebSocket server started on port 8765");
		} catch (Exception e) {
			MinecraftAI.LOGGER.error("Failed to start WebSocket server: " + e.getMessage());
		}

		// Initialize frame capture
		frameCapture = new FrameCapture();
		frameCapture.setFrameCallback(frameData -> {
			if (wsServer != null) {
				wsServer.sendFrame(frameData);
			}
		});
		frameCapture.register();
		wsServer.setFrameCapture(frameCapture);
		MinecraftAI.LOGGER.info("Frame capture initialized (disabled by default, enable via frame_config message)");

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

			// Send state updates every 10 ticks (0.5 seconds)
			if (wsServer != null && client.player != null && client.level.getGameTime() % 10 == 0) {
				Protocol.StateMessage state = actionApplier.getState();
				if (state != null) {
					wsServer.sendState(state);
				}
			}
		});
	}
}
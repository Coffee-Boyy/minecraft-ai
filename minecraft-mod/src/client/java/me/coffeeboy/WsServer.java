package me.coffeeboy;

import org.java_websocket.WebSocket;
import org.java_websocket.handshake.ClientHandshake;
import org.java_websocket.server.WebSocketServer;

import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

public class WsServer extends WebSocketServer {
    private final ConcurrentHashMap<WebSocket, Long> connections = new ConcurrentHashMap<>();
    private final ActionApplier actionApplier;
    private final AtomicInteger frameSequence = new AtomicInteger(0);
    private FrameCapture frameCapture;

    // Binary message type constants
    private static final byte MSG_TYPE_FRAME = 0x01;

    public WsServer(int port, ActionApplier actionApplier) {
        super(new InetSocketAddress(port));
        this.actionApplier = actionApplier;
    }

    @Override
    public void onOpen(WebSocket conn, ClientHandshake handshake) {
        connections.put(conn, System.currentTimeMillis());
        MinecraftAI.LOGGER.info("New client connected: " + conn.getRemoteSocketAddress());
    }

    @Override
    public void onClose(WebSocket conn, int code, String reason, boolean remote) {
        connections.remove(conn);
        MinecraftAI.LOGGER.info("Client disconnected: " + conn.getRemoteSocketAddress());
    }

    @Override
    public void onMessage(WebSocket conn, String message) {
        MinecraftAI.LOGGER.info("Received message: {}", message.substring(0, Math.min(200, message.length())));

        try {
            // Check for frame_config message (handle with or without space after colon)
            boolean isFrameConfig = message.contains("\"type\":\"frame_config\"") ||
                                    message.contains("\"type\": \"frame_config\"");
            MinecraftAI.LOGGER.info("Is frame_config? {}", isFrameConfig);

            if (isFrameConfig) {
                MinecraftAI.LOGGER.info("Processing frame_config message");
                Protocol.FrameConfigMessage config = Protocol.FrameConfigMessage.fromJson(message);
                MinecraftAI.LOGGER.info("Parsed config: enabled={}, {}x{}, every {} frames, quality={}",
                    config.enabled, config.width, config.height, config.captureEveryNFrames, config.jpegQuality);

                if (frameCapture != null) {
                    MinecraftAI.LOGGER.info("Configuring frame capture...");
                    frameCapture.setEnabled(config.enabled);
                    frameCapture.setResolution(config.width, config.height);
                    frameCapture.setCaptureRate(config.captureEveryNFrames);
                    frameCapture.setJpegQuality(config.jpegQuality);
                    MinecraftAI.LOGGER.info("Frame capture configured successfully");
                } else {
                    MinecraftAI.LOGGER.warn("frameCapture is null!");
                }
                return;
            }

            MinecraftAI.LOGGER.info("Not a frame_config, parsing as action message");
            // Parse action message
            Protocol.ActionMessage action = Protocol.ActionMessage.fromJson(message);

            // Apply action via ActionApplier
            actionApplier.applyAction(action, ack -> {
                // Send acknowledgment back to client (only if still connected)
                if (conn.isOpen()) {
                    conn.send(ack.toJson());
                }
            });

        } catch (Exception e) {
            MinecraftAI.LOGGER.error("Error processing message: " + e.getMessage());

            // Send error acknowledgment (only if still connected)
            if (conn.isOpen()) {
                Protocol.AckMessage ack = new Protocol.AckMessage();
                ack.action_type = "unknown";
                ack.success = false;
                ack.error = e.getMessage();
                conn.send(ack.toJson());
            }
        }
    }

    @Override
    public void onError(WebSocket conn, Exception ex) {
        MinecraftAI.LOGGER.error("WebSocket error: " + ex.getMessage());
    }

    @Override
    public void onStart() {
        MinecraftAI.LOGGER.info("WebSocket server started on port " + getPort());
        setConnectionLostTimeout(30);
    }

    public void broadcast(String message) {
        for (WebSocket conn : connections.keySet()) {
            if (conn.isOpen()) {
                conn.send(message);
            }
        }
    }

    public void sendState(Protocol.StateMessage state) {
        broadcast(state.toJson());
    }

    public int getConnectionCount() {
        return connections.size();
    }

    /**
     * Set the frame capture instance for configuration.
     */
    public void setFrameCapture(FrameCapture capture) {
        this.frameCapture = capture;
    }

    /**
     * Send a frame to all connected clients as a binary message.
     * Binary format: type(1) + sequence(4) + timestamp(4) + jpeg_data
     */
    public void sendFrame(byte[] frameData) {
        if (connections.isEmpty()) {
            MinecraftAI.LOGGER.debug("No connections, skipping frame send");
            return;
        }

        int seq = frameSequence.incrementAndGet();
        int timestamp = (int) (System.currentTimeMillis() & 0xFFFFFFFFL);

        MinecraftAI.LOGGER.info("Sending frame: seq={}, timestamp={}, dataLen={} to {} clients",
            seq, timestamp, frameData.length, connections.size());

        // Create binary message: type(1) + seq(4) + ts(4) + data
        ByteBuffer buffer = ByteBuffer.allocate(9 + frameData.length);
        buffer.put(MSG_TYPE_FRAME);
        buffer.putInt(seq);
        buffer.putInt(timestamp);
        buffer.put(frameData);
        buffer.flip();

        for (WebSocket conn : connections.keySet()) {
            try {
                conn.send(buffer.duplicate());
                MinecraftAI.LOGGER.info("Frame sent to client: {}", conn.getRemoteSocketAddress());
            } catch (Exception e) {
                MinecraftAI.LOGGER.warn("Failed to send frame to client: {}", e.getMessage());
            }
        }
    }
}

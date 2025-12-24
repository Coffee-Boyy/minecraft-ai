package me.coffeeboy;

import org.java_websocket.WebSocket;
import org.java_websocket.handshake.ClientHandshake;
import org.java_websocket.server.WebSocketServer;

import java.net.InetSocketAddress;
import java.util.concurrent.ConcurrentHashMap;

public class WsServer extends WebSocketServer {
    private final ConcurrentHashMap<WebSocket, Long> connections = new ConcurrentHashMap<>();
    private final ActionApplier actionApplier;

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
        try {
            // Parse action message
            Protocol.ActionMessage action = Protocol.ActionMessage.fromJson(message);

            // Apply action via ActionApplier
            actionApplier.applyAction(action, ack -> {
                // Send acknowledgment back to client
                conn.send(ack.toJson());
            });

        } catch (Exception e) {
            MinecraftAI.LOGGER.error("Error processing message: " + e.getMessage());

            // Send error acknowledgment
            Protocol.AckMessage ack = new Protocol.AckMessage();
            ack.action_type = "unknown";
            ack.success = false;
            ack.error = e.getMessage();
            conn.send(ack.toJson());
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
            conn.send(message);
        }
    }

    public void sendState(Protocol.StateMessage state) {
        broadcast(state.toJson());
    }

    public int getConnectionCount() {
        return connections.size();
    }
}

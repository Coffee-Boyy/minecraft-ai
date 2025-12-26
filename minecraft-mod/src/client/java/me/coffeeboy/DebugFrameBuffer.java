package me.coffeeboy;

import net.fabricmc.loader.api.FabricLoader;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;

/**
 * Keeps the last N JPEG frames in memory and periodically writes them to disk.
 *
 * Files are written to: <gameDir>/mcagent_frames/frame_0.jpg ... frame_{N-1}.jpg
 * Where frame_0 is the oldest and frame_{N-1} is the newest.
 */
public final class DebugFrameBuffer {
    private final int capacity;
    private final ArrayDeque<byte[]> frames;
    private final Path outDir;

    public DebugFrameBuffer(int capacity, String outputDir) {
        this.capacity = Math.max(1, capacity);
        this.frames = new ArrayDeque<>(this.capacity);
        this.outDir = resolveOutputDir(outputDir);
    }

    public synchronized void addFrame(byte[] jpegBytes) {
        if (jpegBytes == null || jpegBytes.length == 0) return;
        // Copy to avoid any accidental mutation/reuse.
        byte[] copy = new byte[jpegBytes.length];
        System.arraycopy(jpegBytes, 0, copy, 0, jpegBytes.length);

        if (frames.size() == capacity) {
            frames.removeFirst();
        }
        frames.addLast(copy);
    }

    public void writeToDiskBestEffort() {
        try {
            List<byte[]> snapshot = snapshot();
            Files.createDirectories(outDir);

            for (int i = 0; i < snapshot.size(); i++) {
                Path p = outDir.resolve("frame_" + i + ".jpg");
                Files.write(p, snapshot.get(i));
            }
        } catch (Exception e) {
            MinecraftAI.LOGGER.warn("Failed to write debug frames: {}", e.getMessage());
        }
    }

    private synchronized List<byte[]> snapshot() {
        return new ArrayList<>(frames);
    }

    private static Path resolveOutputDir(String outputDir) {
        String dir = (outputDir == null || outputDir.isBlank()) ? "mcagent_frames" : outputDir.trim();
        Path p = Paths.get(dir);
        if (p.isAbsolute()) {
            return p;
        }
        return FabricLoader.getInstance().getGameDir().resolve(p);
    }
}



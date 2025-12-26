package me.coffeeboy;

import net.fabricmc.fabric.api.client.rendering.v1.WorldRenderEvents;
import net.fabricmc.fabric.api.client.screen.v1.ScreenEvents;
import net.minecraft.client.Minecraft;
import org.lwjgl.BufferUtils;
import org.lwjgl.opengl.GL11;

import javax.imageio.IIOImage;
import javax.imageio.ImageIO;
import javax.imageio.ImageWriteParam;
import javax.imageio.ImageWriter;
import javax.imageio.stream.MemoryCacheImageOutputStream;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.util.Iterator;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.function.Consumer;

/**
 * Captures frames from the Minecraft framebuffer and encodes them to JPEG.
 * Frames are captured after world rendering completes and encoded asynchronously.
 */
public class FrameCapture {
    // Configuration
    private volatile int targetWidth = 384;
    private volatile int targetHeight = 216;
    private volatile int captureEveryNFrames = 20;
    private volatile float jpegQuality = 0.5f;
    private volatile boolean enabled = false;

    // State
    private int frameCounter = 0;
    private ByteBuffer pixelBuffer;
    private int lastBufferWidth = 0;
    private int lastBufferHeight = 0;
    private Consumer<byte[]> frameCallback;

    // Timing (best-effort): exposed for metrics/HUD.
    private volatile double lastCaptureMs = 0.0;
    private volatile double lastEncodeMs = 0.0;

    // Async encoding with bounded queue to prevent memory buildup
    private final ExecutorService encoderExecutor;

    public FrameCapture() {
        // Single thread executor with bounded queue - drop frames if encoder can't keep up
        this.encoderExecutor = new ThreadPoolExecutor(
            1, 1,
            0L, TimeUnit.MILLISECONDS,
            new LinkedBlockingQueue<>(2),  // Max 2 pending frames
            r -> {
                Thread t = new Thread(r, "FrameEncoder");
                t.setDaemon(true);
                return t;
            },
            new ThreadPoolExecutor.DiscardOldestPolicy()  // Drop oldest frame if queue full
        );
    }

    /**
     * Register for render events. Must be called during mod initialization.
     */
    public void register() {
        // In-world rendering: fires when a world is being rendered.
        WorldRenderEvents.END.register(context -> maybeCapture());

        // UI/screens rendering (menus, inventory, chat, etc.).
        // This makes "mod capture" work even when the player/world isn't active.
        ScreenEvents.AFTER_INIT.register((client, screen, scaledWidth, scaledHeight) -> {
            ScreenEvents.afterRender(screen).register((s, drawContext, mouseX, mouseY, tickDelta) -> maybeCapture());
        });

        MinecraftAI.LOGGER.info("FrameCapture registered for WorldRenderEvents.END");
    }

    private void maybeCapture() {
        if (!enabled || frameCallback == null) {
            return;
        }

        frameCounter++;
        if (frameCounter % captureEveryNFrames != 0) {
            return;
        }

        captureFrame();
    }

    private void captureFrame() {
        Minecraft mc = Minecraft.getInstance();
        if (mc.getWindow() == null) {
            return;
        }

        long captureStartNs = System.nanoTime();
        int windowWidth = mc.getWindow().getWidth();
        int windowHeight = mc.getWindow().getHeight();

        if (windowWidth <= 0 || windowHeight <= 0) {
            return;
        }

        // Allocate or reallocate buffer if window size changed
        int bufferSize = windowWidth * windowHeight * 4; // RGBA
        if (pixelBuffer == null || lastBufferWidth != windowWidth || lastBufferHeight != windowHeight) {
            pixelBuffer = BufferUtils.createByteBuffer(bufferSize);
            lastBufferWidth = windowWidth;
            lastBufferHeight = windowHeight;
            MinecraftAI.LOGGER.info("FrameCapture buffer allocated: {}x{}", windowWidth, windowHeight);
        }
        pixelBuffer.clear();

        // Read pixels from framebuffer
        GL11.glPixelStorei(GL11.GL_PACK_ALIGNMENT, 1);
        GL11.glReadPixels(0, 0, windowWidth, windowHeight,
            GL11.GL_RGBA, GL11.GL_UNSIGNED_BYTE, pixelBuffer);

        // Copy data for async processing
        byte[] pixelData = new byte[bufferSize];
        pixelBuffer.get(pixelData);
        pixelBuffer.rewind();

        final int w = windowWidth;
        final int h = windowHeight;
        final int tw = targetWidth;
        final int th = targetHeight;
        final float quality = jpegQuality;
        final Consumer<byte[]> callback = frameCallback;
        final double captureMs = (System.nanoTime() - captureStartNs) / 1_000_000.0;

        // Encode asynchronously
        encoderExecutor.submit(() -> {
            long encodeStartNs = System.nanoTime();
            try {
                byte[] encoded = encodeFrame(pixelData, w, h, tw, th, quality);
                lastCaptureMs = captureMs;
                lastEncodeMs = (System.nanoTime() - encodeStartNs) / 1_000_000.0;
                if (encoded != null && callback != null) {
                    callback.accept(encoded);
                }
            } catch (Exception e) {
                MinecraftAI.LOGGER.error("Failed to encode frame: {}", e.getMessage());
            }
        });
    }

    private byte[] encodeFrame(byte[] pixelData, int srcWidth, int srcHeight,
                               int dstWidth, int dstHeight, float quality) {
        // Create BufferedImage at target resolution
        BufferedImage image = new BufferedImage(dstWidth, dstHeight, BufferedImage.TYPE_INT_RGB);

        // Scale factors
        float scaleX = (float) srcWidth / dstWidth;
        float scaleY = (float) srcHeight / dstHeight;

        // Sample and flip (OpenGL origin is bottom-left, BufferedImage is top-left)
        for (int y = 0; y < dstHeight; y++) {
            // Flip Y coordinate
            int srcY = srcHeight - 1 - (int) (y * scaleY);
            if (srcY < 0) srcY = 0;
            if (srcY >= srcHeight) srcY = srcHeight - 1;

            for (int x = 0; x < dstWidth; x++) {
                int srcX = (int) (x * scaleX);
                if (srcX < 0) srcX = 0;
                if (srcX >= srcWidth) srcX = srcWidth - 1;

                int srcIdx = (srcY * srcWidth + srcX) * 4;

                if (srcIdx >= 0 && srcIdx + 2 < pixelData.length) {
                    int r = pixelData[srcIdx] & 0xFF;
                    int g = pixelData[srcIdx + 1] & 0xFF;
                    int b = pixelData[srcIdx + 2] & 0xFF;
                    int rgb = (r << 16) | (g << 8) | b;
                    image.setRGB(x, y, rgb);
                }
            }
        }

        // Encode to JPEG
        try (ByteArrayOutputStream baos = new ByteArrayOutputStream()) {
            Iterator<ImageWriter> writers = ImageIO.getImageWritersByFormatName("jpeg");
            if (!writers.hasNext()) {
                MinecraftAI.LOGGER.error("No JPEG ImageWriter found");
                return null;
            }

            ImageWriter writer = writers.next();
            ImageWriteParam param = writer.getDefaultWriteParam();
            param.setCompressionMode(ImageWriteParam.MODE_EXPLICIT);
            param.setCompressionQuality(quality);

            try (MemoryCacheImageOutputStream output = new MemoryCacheImageOutputStream(baos)) {
                writer.setOutput(output);
                writer.write(null, new IIOImage(image, null, null), param);
            }
            writer.dispose();

            return baos.toByteArray();
        } catch (Exception e) {
            MinecraftAI.LOGGER.error("JPEG encoding failed: {}", e.getMessage());
            return null;
        }
    }

    // Configuration methods

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
        MinecraftAI.LOGGER.info("FrameCapture enabled: {}", enabled);
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setResolution(int width, int height) {
        this.targetWidth = width;
        this.targetHeight = height;
        MinecraftAI.LOGGER.info("FrameCapture resolution: {}x{}", width, height);
    }

    public void setCaptureRate(int everyNFrames) {
        this.captureEveryNFrames = Math.max(1, everyNFrames);
        MinecraftAI.LOGGER.info("FrameCapture rate: every {} frames", captureEveryNFrames);
    }

    public void setJpegQuality(float quality) {
        this.jpegQuality = Math.max(0.0f, Math.min(1.0f, quality));
        MinecraftAI.LOGGER.info("FrameCapture JPEG quality: {}", jpegQuality);
    }

    public void setFrameCallback(Consumer<byte[]> callback) {
        this.frameCallback = callback;
    }

    public double getLastCaptureMs() {
        return lastCaptureMs;
    }

    public double getLastEncodeMs() {
        return lastEncodeMs;
    }

    public void shutdown() {
        enabled = false;
        encoderExecutor.shutdown();
        try {
            if (!encoderExecutor.awaitTermination(1, TimeUnit.SECONDS)) {
                encoderExecutor.shutdownNow();
            }
        } catch (InterruptedException e) {
            encoderExecutor.shutdownNow();
            Thread.currentThread().interrupt();
        }
        MinecraftAI.LOGGER.info("FrameCapture shutdown complete");
    }
}

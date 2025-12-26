package me.coffeeboy;

import net.minecraft.client.KeyMapping;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;

import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.function.Consumer;

public class ActionApplier {
    private final Minecraft minecraft;
    private final ConcurrentLinkedQueue<PendingAction> actionQueue = new ConcurrentLinkedQueue<>();

    // References to movement key bindings (lazily initialized)
    private KeyMapping keyForward;
    private KeyMapping keyBack;
    private KeyMapping keyLeft;
    private KeyMapping keyRight;
    private KeyMapping keyJump;
    private KeyMapping keySneak;
    private KeyMapping keySprint;
    private boolean keysInitialized = false;

    private static class PendingAction {
        Protocol.ActionMessage action;
        Consumer<Protocol.AckMessage> callback;
        long startTime;
        long endTime;

        PendingAction(Protocol.ActionMessage action, Consumer<Protocol.AckMessage> callback) {
            this.action = action;
            this.callback = callback;
            this.startTime = System.currentTimeMillis();
            this.endTime = startTime + action.duration_ms;
        }
    }

    public ActionApplier(Minecraft minecraft) {
        this.minecraft = minecraft;
    }

    private void ensureKeysInitialized() {
        if (!keysInitialized && minecraft.options != null) {
            this.keyForward = minecraft.options.keyUp;
            this.keyBack = minecraft.options.keyDown;
            this.keyLeft = minecraft.options.keyLeft;
            this.keyRight = minecraft.options.keyRight;
            this.keyJump = minecraft.options.keyJump;
            this.keySneak = minecraft.options.keyShift;
            this.keySprint = minecraft.options.keySprint;
            this.keysInitialized = true;
        }
    }

    public void applyAction(Protocol.ActionMessage action, Consumer<Protocol.AckMessage> callback) {
        // Add to queue for processing on game thread
        actionQueue.offer(new PendingAction(action, callback));
    }

    public void tick() {
        LocalPlayer player = minecraft.player;
        if (player == null) {
            // We're not in a world yet (e.g. title screen/loading). Drain any queued
            // actions so the agent doesn't wait forever for acks.
            PendingAction pending;
            while ((pending = actionQueue.poll()) != null) {
                Protocol.AckMessage ack = new Protocol.AckMessage();
                ack.action_type = pending.action.type;
                ack.success = false;
                ack.error = "No player/world loaded";
                pending.callback.accept(ack);
            }
            return;
        }

        // Lazily initialize key bindings once options are available
        ensureKeysInitialized();
        if (!keysInitialized) {
            // Options/keybindings not ready yet; drain queued actions to avoid
            // unbounded queue growth and provide feedback to the agent.
            PendingAction pending;
            while ((pending = actionQueue.poll()) != null) {
                Protocol.AckMessage ack = new Protocol.AckMessage();
                ack.action_type = pending.action.type;
                ack.success = false;
                ack.error = "Key bindings not initialized yet";
                pending.callback.accept(ack);
            }
            return;
        }

        long currentTime = System.currentTimeMillis();

        // Process queued actions
        while (!actionQueue.isEmpty()) {
            PendingAction pending = actionQueue.peek();
            if (pending == null) break;

            // Check if this is a new action or ongoing
            if (currentTime >= pending.endTime) {
                // Action completed, remove from queue
                actionQueue.poll();

                // Send acknowledgment
                Protocol.AckMessage ack = new Protocol.AckMessage();
                ack.action_type = pending.action.type;
                ack.success = true;
                pending.callback.accept(ack);

                // Reset inputs by releasing all simulated key presses
                keyForward.setDown(false);
                keyBack.setDown(false);
                keyLeft.setDown(false);
                keyRight.setDown(false);
                keyJump.setDown(false);
                keySneak.setDown(false);
                keySprint.setDown(false);

                continue;
            }

            // Apply the action for this tick
            Protocol.ActionMessage action = pending.action;

            // Movement - simulate key presses via KeyMapping.setDown()
            keyForward.setDown(action.forward > 0);
            keyBack.setDown(action.forward < 0);
            // strafe: negative=left, positive=right
            keyLeft.setDown(action.strafe < 0);
            keyRight.setDown(action.strafe > 0);

            // Look
            if (action.yaw != 0 || action.pitch != 0) {
                // Treat yaw/pitch as absolute angles (matches the agent schema and Minecraft convention).
                float newYaw = action.yaw;
                float newPitch = Math.max(-90.0F, Math.min(90.0F, action.pitch));
                player.setYRot(newYaw);
                player.setXRot(newPitch);
                player.yRotO = newYaw;
                player.xRotO = newPitch;
            }

            // Jump
            keyJump.setDown(action.jump);

            // Attack (left click)
            if (action.attack && minecraft.gameMode != null) {
                var hitResult = player.pick(4.5, 0, false);
                if (hitResult instanceof net.minecraft.world.phys.EntityHitResult entityHit) {
                    minecraft.gameMode.attack(player, entityHit.getEntity());
                } else if (hitResult instanceof net.minecraft.world.phys.BlockHitResult) {
                    // Just swing for blocks
                    player.swing(net.minecraft.world.InteractionHand.MAIN_HAND);
                }
            }

            // Use (right click)
            if (action.use && minecraft.gameMode != null) {
                minecraft.gameMode.useItem(player, player.getUsedItemHand());
            }

            // Sneak
            keySneak.setDown(action.sneak);

            // Sprint
            keySprint.setDown(action.sprint);

            // Only process the first action in queue per tick
            break;
        }
    }

    public Protocol.StateMessage getState() {
        LocalPlayer player = minecraft.player;
        if (player == null || minecraft.level == null) {
            return null;
        }

        Protocol.StateMessage state = new Protocol.StateMessage();

        // Player state
        state.player = new Protocol.PlayerState();
        state.player.x = player.getX();
        state.player.y = player.getY();
        state.player.z = player.getZ();
        state.player.yaw = player.getYRot();
        state.player.pitch = player.getXRot();
        state.player.health = player.getHealth();
        state.player.food = player.getFoodData().getFoodLevel();
        state.player.experience_level = player.experienceLevel;
        state.player.on_ground = player.onGround();
        state.player.in_water = player.isInWater();
        state.player.in_lava = player.isInLava();

        // World state
        state.world = new Protocol.WorldState();
        state.world.dimension = minecraft.level.dimension().toString();
        state.world.time = minecraft.level.getDayTime();
        state.world.is_raining = minecraft.level.isRaining();
        state.world.is_thundering = minecraft.level.isThundering();

        return state;
    }
}

# dobotkit — Magician Lite (arm)

Pure-Python control library for the Dobot **Magician Lite** robotic arm. The arm
is driven through **DobotLink** (no DLL, no direct serial); DobotLink handles the
controller↔MagicBox routing that raw serial cannot.

## Language

**Magician Lite**:
The 4-axis arm this library controls. On a PC it presents as a *Controller*
(master) with the *MagicBox* as its peripheral hub (slave). Distinct from the
classic *Magician*, which is a single directly-addressed device.
_Avoid_: Dobot, robot (too generic).

**DobotLink**:
Dobot's desktop bridge service (WebSocket JSON-RPC on `ws://localhost:9090`).
The library talks to DobotLink; DobotLink talks to the hardware. It must be
running. The arm's RPC surface is the `dobotlink.Magician.*` namespace.
_Avoid_: DobotLab (that is the GUI app; DobotLink is the service it embeds).

**MagicBox**:
The Magician Lite's peripheral hub. Sensors, the external servo, and analog
inputs are wired to it and are reached only through DobotLink's slave routing.
_Avoid_: hub, dock.

## Flagged ambiguities

**Buzzer** — NOT a Magician Lite capability. The Dobot SDK/DLL exposes **no**
buzzer/beep/tone function; `beep` exists only in the separate **AIStarter**
(K210 AI-camera kit), an independent Arduino device. A buzzer is therefore out
of scope for this library unless it is wired to a MagicBox IO pin, in which case
it is just a digital output (`io.set_do`), not a distinct "buzzer" concept.

## Example dialogue

> **Dev:** The kit has a buzzer — should `Magician` get a `buzzer()` method?
> **Expert:** That buzzer is on the AIStarter camera kit, not the arm. The arm
> (Magician Lite) has no buzzer in the SDK. So no — leave it out.
> **Dev:** And a sensor like the potentiometer?
> **Expert:** That's an analog input on the MagicBox. You read it through
> DobotLink, not off the arm controller directly.

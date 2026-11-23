// A persistent scene. All vehicle meshes transform together between solves.
export default function ({ parentElement, data }) {
    const host = parentElement.querySelector(".bridge-live-scene");
    const graph = host.querySelector(".bridge-live-plot");
    const label = host.querySelector(".bridge-live-position");
    let state = host.bridgeAnimation;
    if (!state) {
        state = { ready: false, busy: false, frame: 0, draws: 0, mounted: 0 };
        host.bridgeAnimation = state;
    }
    state.mounted += 1;
    const generation = state.mounted;
    const now = performance.now();
    const token = JSON.stringify(data.clock.run);
    if (state.token !== token || state.playing !== data.clock.playing || !data.clock.playing) {
        state.origin = data.clock.fraction;
        state.started = now;
    }
    state.token = token;
    state.playing = data.clock.playing;
    state.received = now;
    state.packet = data;
    state.pending = data.figure;
    let cancelled = false;
    let ownFrame = 0;

    function frontAt(time) {
        const c = state.packet.clock;
        // Freeze prediction if disconnected rather than inventing more history.
        const until = Math.min(time, state.received + 1000);
        const elapsed = state.playing ? Math.max(0, until - state.started) / 1000 : 0;
        const fraction = Math.min(1, state.origin + elapsed * c.rate);
        return c.lo + (c.hi - c.lo) * fraction;
    }

    function pose(trace, front) {
        const base = trace.meta.front;
        const x = trace.x.map(v => v + front - base);
        const z = [...trace.z];
        const angle = -front / (trace.meta.wheel_radius || 0.42);
        const sin = Math.sin(angle), cos = Math.cos(angle);
        for (const wheel of trace.meta.wheels) {
            for (let i = wheel.start; i < wheel.stop; i++) {
                const dx = trace.x[i] - base - wheel.x;
                const dz = trace.z[i] - wheel.z;
                x[i] = front + wheel.x + dx * cos - dz * sin;
                z[i] = wheel.z + dx * sin + dz * cos;
            }
        }
        return { x, z };
    }

    function report(front) {
        state.draws++;
        host.dataset.frames = String(state.draws);
        host.dataset.frontX = String(front);
        host.dataset.playing = String(state.playing);
        host.dataset.vehicleCount = String(state.vehicles?.length || 0);
        const waiting = state.playing && performance.now() - state.received > 1000;
        const reference = state.packet.clock.vehicle_count > 1 ? "lead front" : "front";
        label.textContent = `Visual ${reference} x = ${front.toFixed(3)} m · ` +
            `results / colors at x = ${state.packet.clock.solved.toFixed(3)} m` +
            (waiting ? " · waiting for server" : "");
    }

    function renderSnapshot(front) {
        const figure = state.pending;
        state.pending = null;
        // Preserve the user's orbit/zoom across numerical response updates.
        const cameraKey = `${state.packet.fit}-${state.packet.camera}`;
        if (state.ready && state.cameraKey === cameraKey && graph.layout?.scene?.camera) {
            figure.layout.scene.camera = graph.layout.scene.camera;
        }
        state.cameraKey = cameraKey;
        state.vehicles = figure.data.flatMap((trace, index) =>
            trace.meta?.role === "vehicle" ?
                [{index, template: structuredClone(trace), offset: trace.meta.front_offset_m || 0}] : []
        );
        for (const vehicle of state.vehicles) {
            Object.assign(figure.data[vehicle.index], pose(vehicle.template, front - vehicle.offset));
        }
        if (state.packet.camera === "Follow vehicle") {
            figure.layout.scene.camera.center.x =
                (front - (state.packet.clock.lo + state.packet.clock.hi) / 2) /
                Math.max(state.packet.clock.hi - state.packet.clock.lo, 1);
        }
        return window.Plotly.react(graph, figure.data, figure.layout, {
            ...state.packet.config, responsive: false,
        }).then(() => { state.ready = true; report(front); });
    }

    async function update(time) {
        if (cancelled || generation !== state.mounted || !host.isConnected) return;
        ownFrame = requestAnimationFrame(update);
        state.frame = ownFrame;
        if (state.busy || !window.Plotly) return;
        const front = frontAt(time);
        if (!state.pending && (!state.playing || !state.vehicles?.length)) return;
        // Do not queue more WebGL work than the browser can finish.
        state.busy = true;
        try {
            if (state.pending) {
                await renderSnapshot(front);
            } else {
                const indices = state.vehicles.map(vehicle => vehicle.index);
                const geometries = state.vehicles.map(vehicle =>
                    pose(vehicle.template, front - vehicle.offset)
                );
                const update = {x: geometries.map(g => g.x), z: geometries.map(g => g.z)};
                if (state.packet.camera === "Follow vehicle") {
                    await window.Plotly.update(
                        graph, update,
                        { "scene.camera.center.x":
                            (front - (state.packet.clock.lo + state.packet.clock.hi) / 2) /
                            Math.max(state.packet.clock.hi - state.packet.clock.lo, 1) },
                        indices,
                    );
                } else {
                    await window.Plotly.restyle(
                        graph, update, indices,
                    );
                }
                report(front);
            }
        } catch (error) {
            label.textContent = `3D rendering error: ${error.message}`;
            host.dataset.error = error.message;
        } finally {
            state.busy = false;
        }
    }

    cancelAnimationFrame(state.frame);
    ownFrame = requestAnimationFrame(update);
    state.frame = ownFrame;
    const resize = new ResizeObserver(() => {
        if (state.ready && !state.busy && graph.isConnected &&
            graph.getClientRects().length && graph.clientWidth && graph.clientHeight) {
            // Plotly debounces resize; the tab may be hidden before it executes.
            window.Plotly.Plots.resize(graph).catch(error => {
                if (!String(error).includes("Resize must be passed")) {
                    host.dataset.error = String(error);
                }
            });
        }
    });
    resize.observe(host);
    return () => {
        cancelled = true;
        cancelAnimationFrame(ownFrame);
        resize.disconnect();
        // Data updates retain the graph. Release GPU resources only on unmount.
        setTimeout(() => {
            if (!host.isConnected && state.ready) window.Plotly.purge(graph);
        }, 0);
    };
}

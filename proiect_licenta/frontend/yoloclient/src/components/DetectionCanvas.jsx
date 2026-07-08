import React, { useRef, useEffect } from "react";

/**
 * Premium animated background — Crowd Counting, Tracking & Re-Identification visualization.
 * Shows: top-down crowd dots with tracking trails, unique IDs, heatmap glow zones,
 * re-identification arcs, live counters, detection brackets, data streams.
 */
export default function DetectionCanvas() {
  const canvasRef = useRef(null);
  const animationRef = useRef(null);
  const mouseRef = useRef({ x: -9999, y: -9999 });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    let W, H;

    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      W = canvas.offsetWidth;
      H = canvas.offsetHeight;
      canvas.width = W * dpr;
      canvas.height = H * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    window.addEventListener("resize", resize);

    const handleMouse = (e) => {
      const rect = canvas.getBoundingClientRect();
      mouseRef.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    };
    canvas.addEventListener("mousemove", handleMouse);

    // ─── CROWD DOTS (top-down people) ───
    const CROWD_COUNT = 70;
    const crowd = [];
    const colors = [
      [0, 230, 118],   // green
      [105, 240, 174],  // emerald
      [43, 236, 132],  // teal-ish
      [0, 200, 83],  // light green
      [0, 168, 68],  // cyan-green
    ];

    for (let i = 0; i < CROWD_COUNT; i++) {
      const color = colors[Math.floor(Math.random() * colors.length)];
      const zone = Math.floor(Math.random() * 3); // 0=left, 1=center, 2=right
      crowd.push({
        x: Math.random() * 2000,
        y: Math.random() * 2000,
        vx: (Math.random() - 0.5) * 0.6,
        vy: (Math.random() - 0.5) * 0.6,
        targetX: null,
        targetY: null,
        id: 100 + i,
        color,
        radius: 2.5 + Math.random() * 2,
        trail: [],
        maxTrail: 15 + Math.floor(Math.random() * 20),
        zone,
        reIdTarget: null,
        reIdTimer: 0,
        pulsePhase: Math.random() * Math.PI * 2,
      });
    }

    // ─── HEATMAP ZONES ───
    const heatZones = [
      { x: 0.2, y: 0.4, r: 0.15, intensity: 0 },
      { x: 0.6, y: 0.6, r: 0.18, intensity: 0 },
      { x: 0.8, y: 0.3, r: 0.12, intensity: 0 },
      { x: 0.4, y: 0.75, r: 0.14, intensity: 0 },
    ];

    // ─── DETECTION EVENTS ───
    const detections = [];
    const spawnDetection = (x, y) => {
      detections.push({ x, y, life: 1, size: 0 });
    };

    // ─── RE-ID ARCS ───
    const reIdArcs = [];
    const spawnReId = (from, to) => {
      reIdArcs.push({
        x1: from.x, y1: from.y, x2: to.x, y2: to.y,
        life: 1, id: from.id,
      });
    };

    // ─── COUNTERS ───
    let totalCount = 0;
    let displayCount = 0;
    let peakCount = 0;
    let reIdCount = 0;

    // ─── FLOWING DATA LINES (vertical) ───
    const dataStreams = [];
    for (let i = 0; i < 8; i++) {
      dataStreams.push({
        x: Math.random() * 2000,
        chars: [],
        nextSpawn: 0,
      });
    }

    let frame = 0;

    const animate = () => {
      frame++;
      ctx.clearRect(0, 0, W, H);

      // ── Background gradient ──
      const bgGrad = ctx.createRadialGradient(W * 0.5, H * 0.5, 0, W * 0.5, H * 0.5, Math.max(W, H) * 0.8);
      bgGrad.addColorStop(0, "rgba(4, 15, 8, 0.4)");
      bgGrad.addColorStop(1, "transparent");
      ctx.fillStyle = bgGrad;
      ctx.fillRect(0, 0, W, H);

      // ── Grid ──
      ctx.strokeStyle = "rgba(0, 230, 118, 0.02)";
      ctx.lineWidth = 0.5;
      const gs = 45;
      for (let x = 0; x < W; x += gs) {
        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke();
      }
      for (let y = 0; y < H; y += gs) {
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
      }

      // ── Camera zone dividers ──
      const zoneW = W / 3;
      for (let i = 1; i <= 2; i++) {
        ctx.setLineDash([8, 12]);
        ctx.strokeStyle = "rgba(0, 230, 118, 0.06)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(zoneW * i, 0);
        ctx.lineTo(zoneW * i, H);
        ctx.stroke();
        ctx.setLineDash([]);

        // Zone labels
        ctx.font = "700 8px 'JetBrains Mono', monospace";
        ctx.fillStyle = "rgba(0, 230, 118, 0.08)";
        ctx.fillText(`CAM_0${i}`, zoneW * (i - 1) + 8, H - 10);
      }
      ctx.fillText("CAM_03", zoneW * 2 + 8, H - 10);

      // ── Heatmap zones ──
      heatZones.forEach((hz) => {
        // Count nearby crowd
        let nearby = 0;
        crowd.forEach((c) => {
          const d = Math.hypot(c.x - hz.x * W, c.y - hz.y * H);
          if (d < hz.r * W) nearby++;
        });
        hz.intensity += (nearby / 15 - hz.intensity) * 0.03;
        const intensity = Math.min(hz.intensity, 1);

        if (intensity > 0.05) {
          const hGrad = ctx.createRadialGradient(
            hz.x * W, hz.y * H, 0,
            hz.x * W, hz.y * H, hz.r * W
          );
          // Color from green -> yellow -> red based on density
          const r = Math.min(255, intensity * 400);
          const g = Math.max(50, 200 - intensity * 200);
          hGrad.addColorStop(0, `rgba(${r}, ${g}, 40, ${intensity * 0.08})`);
          hGrad.addColorStop(0.6, `rgba(${r}, ${g}, 40, ${intensity * 0.03})`);
          hGrad.addColorStop(1, "transparent");
          ctx.fillStyle = hGrad;
          ctx.fillRect(0, 0, W, H);
        }
      });

      // ── Scan line ──
      const scanY = ((frame * 0.6) % (H + 80)) - 40;
      const scanGrad = ctx.createLinearGradient(0, scanY - 30, 0, scanY + 30);
      scanGrad.addColorStop(0, "rgba(0, 230, 118, 0)");
      scanGrad.addColorStop(0.5, "rgba(0, 230, 118, 0.05)");
      scanGrad.addColorStop(1, "rgba(0, 230, 118, 0)");
      ctx.fillStyle = scanGrad;
      ctx.fillRect(0, scanY - 30, W, 60);

      // ── Update & draw crowd ──
      const mouse = mouseRef.current;
      let visibleCount = 0;

      crowd.forEach((person, idx) => {
        // Wandering behavior
        if (!person.targetX || Math.hypot(person.x - person.targetX, person.y - person.targetY) < 20) {
          person.targetX = 30 + Math.random() * (W - 60);
          person.targetY = 30 + Math.random() * (H - 60);
        }
        const dx = person.targetX - person.x;
        const dy = person.targetY - person.y;
        const dist = Math.hypot(dx, dy);
        if (dist > 0) {
          person.vx += (dx / dist) * 0.02;
          person.vy += (dy / dist) * 0.02;
        }

        // Mouse attraction (slight)
        const mdx = mouse.x - person.x;
        const mdy = mouse.y - person.y;
        const mDist = Math.hypot(mdx, mdy);
        if (mDist < 150 && mDist > 0) {
          person.vx += (mdx / mDist) * 0.03;
          person.vy += (mdy / mDist) * 0.03;
        }

        // Crowd avoidance
        crowd.forEach((other, j) => {
          if (idx === j) return;
          const ox = person.x - other.x;
          const oy = person.y - other.y;
          const od = Math.hypot(ox, oy);
          if (od < 18 && od > 0) {
            person.vx += (ox / od) * 0.15;
            person.vy += (oy / od) * 0.15;
          }
        });

        // Damping
        person.vx *= 0.96;
        person.vy *= 0.96;
        const speed = Math.hypot(person.vx, person.vy);
        if (speed > 1.5) {
          person.vx *= 1.5 / speed;
          person.vy *= 1.5 / speed;
        }

        person.x += person.vx;
        person.y += person.vy;
        person.pulsePhase += 0.03;

        // Wrap
        if (person.x < -10) person.x = W + 10;
        if (person.x > W + 10) person.x = -10;
        if (person.y < -10) person.y = H + 10;
        if (person.y > H + 10) person.y = -10;

        // Trail
        person.trail.push({ x: person.x, y: person.y });
        if (person.trail.length > person.maxTrail) person.trail.shift();

        // Check if visible
        if (person.x > 0 && person.x < W && person.y > 0 && person.y < H) {
          visibleCount++;
        }

        // Scan line detection effect
        if (Math.abs(person.y - scanY) < 5 && frame % 3 === 0) {
          spawnDetection(person.x, person.y);
        }

        // Random re-id events
        if (frame % 200 === idx % 200 && !person.reIdTarget) {
          // Find someone in a different zone
          const zoneX = person.x / zoneW;
          const currentZone = Math.floor(zoneX);
          const candidates = crowd.filter((c, ci) => {
            const cz = Math.floor(c.x / zoneW);
            return ci !== idx && cz !== currentZone && Math.abs(c.id - person.id) < 30;
          });
          if (candidates.length > 0) {
            const target = candidates[Math.floor(Math.random() * candidates.length)];
            spawnReId(person, target);
            reIdCount++;
          }
        }

        // ── Draw trail ──
        if (person.trail.length > 2) {
          ctx.beginPath();
          ctx.moveTo(person.trail[0].x, person.trail[0].y);
          for (let k = 1; k < person.trail.length; k++) {
            ctx.lineTo(person.trail[k].x, person.trail[k].y);
          }
          ctx.strokeStyle = `rgba(${person.color[0]}, ${person.color[1]}, ${person.color[2]}, 0.08)`;
          ctx.lineWidth = 1;
          ctx.stroke();
        }

        // ── Draw person dot ──
        const pulse = Math.sin(person.pulsePhase);
        const r = person.radius + pulse * 0.5;

        // Outer glow
        ctx.beginPath();
        ctx.arc(person.x, person.y, r * 3, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${person.color[0]}, ${person.color[1]}, ${person.color[2]}, 0.04)`;
        ctx.fill();

        // Inner dot
        ctx.beginPath();
        ctx.arc(person.x, person.y, r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${person.color[0]}, ${person.color[1]}, ${person.color[2]}, 0.45)`;
        ctx.fill();

        // Core bright dot
        ctx.beginPath();
        ctx.arc(person.x, person.y, r * 0.4, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${person.color[0]}, ${person.color[1]}, ${person.color[2]}, 0.8)`;
        ctx.fill();

        // ID label (show on every Nth person)
        if (idx % 4 === 0) {
          ctx.font = "600 7px 'JetBrains Mono', monospace";
          ctx.fillStyle = `rgba(${person.color[0]}, ${person.color[1]}, ${person.color[2]}, 0.25)`;
          ctx.fillText(`ID:${person.id}`, person.x + r + 3, person.y - 2);
        }
      });

      // ── Detection events (expanding rings) ──
      for (let i = detections.length - 1; i >= 0; i--) {
        const det = detections[i];
        det.life -= 0.02;
        det.size += 0.8;
        if (det.life <= 0) { detections.splice(i, 1); continue; }

        // Corner brackets
        const s = det.size;
        const c = Math.min(6, s * 0.3);
        const alpha = det.life * 0.35;
        ctx.strokeStyle = `rgba(0, 230, 118, ${alpha})`;
        ctx.lineWidth = 1;

        const bx = det.x - s / 2, by = det.y - s / 2;
        // TL
        ctx.beginPath(); ctx.moveTo(bx, by + c); ctx.lineTo(bx, by); ctx.lineTo(bx + c, by); ctx.stroke();
        // TR
        ctx.beginPath(); ctx.moveTo(bx + s - c, by); ctx.lineTo(bx + s, by); ctx.lineTo(bx + s, by + c); ctx.stroke();
        // BL
        ctx.beginPath(); ctx.moveTo(bx, by + s - c); ctx.lineTo(bx, by + s); ctx.lineTo(bx + c, by + s); ctx.stroke();
        // BR
        ctx.beginPath(); ctx.moveTo(bx + s - c, by + s); ctx.lineTo(bx + s, by + s); ctx.lineTo(bx + s, by + s - c); ctx.stroke();
      }

      // ── Re-ID arcs (dashed curves connecting people across zones) ──
      for (let i = reIdArcs.length - 1; i >= 0; i--) {
        const arc = reIdArcs[i];
        arc.life -= 0.008;
        if (arc.life <= 0) { reIdArcs.splice(i, 1); continue; }

        const alpha = arc.life * 0.2;
        const midX = (arc.x1 + arc.x2) / 2;
        const midY = Math.min(arc.y1, arc.y2) - 40 - Math.abs(arc.x2 - arc.x1) * 0.15;

        ctx.setLineDash([4, 6]);
        ctx.beginPath();
        ctx.moveTo(arc.x1, arc.y1);
        ctx.quadraticCurveTo(midX, midY, arc.x2, arc.y2);
        ctx.strokeStyle = `rgba(105, 240, 174, ${alpha})`;
        ctx.lineWidth = 1;
        ctx.stroke();
        ctx.setLineDash([]);

        // ReID label at midpoint
        if (arc.life > 0.5) {
          const labelX = midX;
          const labelY = midY + (arc.y1 + arc.y2) / 2 * 0.02;
          ctx.font = "700 7px 'JetBrains Mono', monospace";
          ctx.fillStyle = `rgba(105, 240, 174, ${alpha * 1.5})`;
          ctx.textAlign = "center";
          ctx.fillText(`RE-ID #${arc.id}`, labelX, midY - 4);
          ctx.textAlign = "left";
        }
      }

      // ── Data streams (Matrix-style vertical) ──
      dataStreams.forEach((stream) => {
        stream.x = stream.x || Math.random() * W;
        if (stream.x > W) stream.x = Math.random() * W;

        stream.nextSpawn--;
        if (stream.nextSpawn <= 0) {
          stream.chars.push({ y: -10, char: String.fromCharCode(48 + Math.floor(Math.random() * 10)), alpha: 0.15 + Math.random() * 0.1 });
          stream.nextSpawn = 8 + Math.floor(Math.random() * 15);
        }

        stream.chars.forEach((ch) => {
          ch.y += 0.5;
          ctx.font = "500 9px 'JetBrains Mono', monospace";
          ctx.fillStyle = `rgba(0, 230, 118, ${ch.alpha * Math.max(0, 1 - ch.y / H)})`;
          ctx.fillText(ch.char, stream.x, ch.y);
        });
        stream.chars = stream.chars.filter((ch) => ch.y < H);
      });

      // ── Counters ──
      totalCount = visibleCount;
      displayCount += (totalCount - displayCount) * 0.05;
      if (totalCount > peakCount) peakCount = totalCount;

      // ── HUD ──
      ctx.font = "700 9px 'JetBrains Mono', monospace";

      // Top-left
      ctx.fillStyle = "rgba(0, 230, 118, 0.2)";
      ctx.fillText("CROWD_DETECTION_SYSTEM", 12, 18);
      ctx.fillStyle = "rgba(0, 230, 118, 0.15)";
      ctx.fillText(`TRACKING: MULTI-CAM`, 12, 32);
      ctx.fillText(`PERSONS: ${Math.round(displayCount)}`, 12, 46);
      ctx.fillText(`PEAK: ${peakCount}`, 12, 60);

      // Top-right
      ctx.textAlign = "right";
      ctx.fillStyle = "rgba(0, 230, 118, 0.2)";
      const fps = (30 + Math.sin(frame * 0.02) * 5).toFixed(0);
      ctx.fillText(`${fps} FPS`, W - 12, 18);
      ctx.fillStyle = "rgba(0, 230, 118, 0.15)";
      ctx.fillText(`RE-ID: ${reIdCount}`, W - 12, 32);
      ctx.fillText(`DENSITY: ${(displayCount / Math.max(1, (W * H) / 10000)).toFixed(2)}`, W - 12, 46);
      ctx.fillText("STREAM: LIVE", W - 12, 60);
      ctx.textAlign = "left";

      // Bottom-left mini bar chart (density per zone)
      const barY = H - 55;
      const barH = 30;
      const barW = 35;
      ctx.fillStyle = "rgba(0, 230, 118, 0.1)";
      ctx.font = "600 7px 'JetBrains Mono', monospace";
      ctx.fillText("DENSITY/ZONE", 12, barY - 6);
      for (let z = 0; z < 3; z++) {
        const zoneCount = crowd.filter((c) => {
          const cz = Math.floor(c.x / zoneW);
          return cz === z && c.x > 0 && c.x < W && c.y > 0 && c.y < H;
        }).length;
        const h = Math.min(barH, (zoneCount / 30) * barH);
        ctx.fillStyle = `rgba(0, 230, 118, 0.08)`;
        ctx.fillRect(12 + z * (barW + 4), barY + barH - h, barW, h);
        ctx.strokeStyle = "rgba(0, 230, 118, 0.12)";
        ctx.lineWidth = 0.5;
        ctx.strokeRect(12 + z * (barW + 4), barY, barW, barH);
        ctx.fillStyle = "rgba(0, 230, 118, 0.12)";
        ctx.fillText(`${zoneCount}`, 12 + z * (barW + 4) + barW / 2 - 4, barY + barH + 10);
      }

      animationRef.current = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      window.removeEventListener("resize", resize);
      canvas.removeEventListener("mousemove", handleMouse);
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: "absolute",
        inset: 0,
        width: "100%",
        height: "100%",
        zIndex: 0,
      }}
    />
  );
}

import { Suspense, useEffect, useRef, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { Float, MeshDistortMaterial, Sparkles } from "@react-three/drei";

function EnergyOrb() {
  return (
    <Float speed={1.4} rotationIntensity={0.6} floatIntensity={1.2}>
      <mesh>
        <icosahedronGeometry args={[1.4, 8]} />
        <MeshDistortMaterial
          color="#7c5cff"
          emissive="#4c2fcf"
          emissiveIntensity={0.5}
          roughness={0.15}
          metalness={0.4}
          distort={0.45}
          speed={2}
        />
      </mesh>
    </Float>
  );
}

/**
 * Purely decorative WebGL hero background for the landing screen -- an
 * abstract glowing orb plus ambient particles. Rendered behind the hero
 * copy (see Landing.tsx / global.css `.hero__canvas`), never load-bearing
 * for functionality, so Suspense's fallback is just `null`.
 *
 * A WebGL canvas keeps re-rendering every frame via requestAnimationFrame
 * for as long as it's mounted, even when scrolled completely out of view --
 * the browser doesn't throttle that on its own. With more sections added
 * below the hero, that background rendering competed with scroll
 * compositing for main-thread/GPU time and made scrolling feel sluggish.
 * An IntersectionObserver flips the render loop off via `frameloop="never"`
 * once the hero scrolls out of view (keeping the canvas mounted, so there's
 * no WebGL context re-init cost when it scrolls back in) and back on when
 * it's visible again.
 */
export function HeroScene() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [isVisible, setIsVisible] = useState(true);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(([entry]) => setIsVisible(entry.isIntersecting), {
      threshold: 0,
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div className="hero__canvas" aria-hidden="true" ref={containerRef}>
      <Canvas
        camera={{ position: [0, 0, 5], fov: 45 }}
        dpr={1}
        frameloop={isVisible ? "always" : "never"}
      >
        <ambientLight intensity={0.6} />
        <pointLight position={[5, 5, 5]} intensity={1.2} color="#7c5cff" />
        <pointLight position={[-5, -3, -5]} intensity={0.6} color="#22d3ee" />
        <Suspense fallback={null}>
          <EnergyOrb />
          <Sparkles count={60} scale={[8, 5, 4]} size={2} speed={0.3} color="#22d3ee" />
        </Suspense>
      </Canvas>
    </div>
  );
}

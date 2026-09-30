import { useEffect, useRef, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { Float, Sparkles } from "@react-three/drei";

/** A low-poly shape: a flat-shaded icosahedron (80 faces) with a wireframe shell. */
function LowPolyShape() {
  return (
    <Float speed={1.2} rotationIntensity={0.8} floatIntensity={1}>
      <mesh>
        <icosahedronGeometry args={[1.5, 1]} />
        <meshStandardMaterial color="#c8ff3d" flatShading roughness={0.35} metalness={0.2} />
      </mesh>
      <mesh scale={1.22}>
        <icosahedronGeometry args={[1.5, 1]} />
        <meshBasicMaterial color="#10b981" wireframe transparent opacity={0.25} />
      </mesh>
    </Float>
  );
}

/**
 * Decorative WebGL hero background. Loaded lazily (React.lazy in Hero.tsx), so three.js is a
 * separate chunk that never delays the first paint. It only renders while visible
 * (IntersectionObserver -> frameloop "never" off-screen), and renders a single still frame
 * when the user prefers reduced motion.
 */
export default function HeroCanvas({ reducedMotion }: { reducedMotion: boolean }) {
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    const el = wrapperRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const frameloop = reducedMotion ? "demand" : visible ? "always" : "never";

  return (
    <div ref={wrapperRef} className="absolute inset-0" aria-hidden>
      <Canvas frameloop={frameloop} dpr={[1, 1.5]} camera={{ position: [0, 0, 6.8], fov: 45 }}>
        <ambientLight intensity={0.45} />
        <directionalLight position={[3, 4, 5]} intensity={1.6} />
        <directionalLight position={[-4, -2, -3]} intensity={0.6} color="#10b981" />
        <LowPolyShape />
        {!reducedMotion && <Sparkles count={40} scale={7} size={2} speed={0.3} color="#c8ff3d" />}
      </Canvas>
    </div>
  );
}

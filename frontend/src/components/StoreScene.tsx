import { Html, OrbitControls, useAnimations, useGLTF } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { clone } from "three/examples/jsm/utils/SkeletonUtils.js";

import type {
  CustomerAgent,
  Equipment,
  EquipmentState,
  Position,
  StaffAgent,
  Store,
  WorldState,
} from "../types";

type Selection = { kind: "staff" | "customer" | "equipment"; id: string } | null;

const MODEL_BASE = `${import.meta.env.BASE_URL}models/`;
const MODEL_URLS = {
  manager: `${MODEL_BASE}shift-manager.glb`,
  associate: `${MODEL_BASE}associate.glb`,
  customer_01: `${MODEL_BASE}purposeful-shopper.glb`,
  customer_02: `${MODEL_BASE}display-browser.glb`,
  customer_03: `${MODEL_BASE}value-seeker.glb`,
  customer_04: `${MODEL_BASE}late-browser.glb`,
} as const;

function AnimatedCharacter({
  url,
  position,
  scale,
  accent,
  selected,
  onSelect,
}: {
  url: string;
  position: Position;
  scale: number;
  accent: string;
  selected: boolean;
  onSelect: () => void;
}) {
  const movementRoot = useRef<THREE.Group>(null);
  const animationRoot = useRef<THREE.Group>(null);
  const moving = useRef(false);
  const target = useMemo(() => new THREE.Vector3(position.x, 0, position.z), [position]);
  const { scene, animations } = useGLTF(url);
  const character = useMemo(() => {
    const instance = clone(scene);
    instance.traverse((object) => {
      if (object instanceof THREE.Mesh) {
        object.castShadow = true;
        object.receiveShadow = true;
      }
    });
    return instance;
  }, [scene]);
  const { actions } = useAnimations(animations, animationRoot);

  useEffect(() => {
    const idle = actions["Armature|Idle"];
    idle?.reset().fadeIn(0.2).play();
    return () => {
      idle?.fadeOut(0.1);
    };
  }, [actions]);

  useFrame((_, delta) => {
    const root = movementRoot.current;
    if (!root) return;
    const isMoving = root.position.distanceTo(target) > 0.035;
    if (isMoving) {
      root.lookAt(target.x, 0, target.z);
      root.position.lerp(target, 1 - Math.exp(-5.5 * delta));
    }
    if (isMoving === moving.current) return;
    const previous = actions[moving.current ? "Armature|Walk" : "Armature|Idle"];
    const next = actions[isMoving ? "Armature|Walk" : "Armature|Idle"];
    previous?.fadeOut(0.18);
    next?.reset().fadeIn(0.18).play();
    moving.current = isMoving;
  });

  return (
    <group
      ref={movementRoot}
      position={[position.x, 0, position.z]}
      onClick={(event) => {
        event.stopPropagation();
        onSelect();
      }}
    >
      <group ref={animationRoot} scale={scale} rotation={[0, Math.PI, 0]}>
        <primitive object={character} />
      </group>
      <mesh position={[0, 0.025, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.3, selected ? 0.5 : 0.37, 28]} />
        <meshBasicMaterial color={accent} transparent opacity={selected ? 0.95 : 0.68} />
      </mesh>
    </group>
  );
}

function StoreAgent({
  agent,
  position,
  selected,
  onSelect,
}: {
  agent: StaffAgent;
  position: Position;
  selected: boolean;
  onSelect: () => void;
}) {
  const manager = agent.role === "manager";
  return (
    <AnimatedCharacter
      url={manager ? MODEL_URLS.manager : MODEL_URLS.associate}
      position={position}
      scale={manager ? 0.76 : 0.74}
      accent={manager ? "#ffd36b" : "#79f2b5"}
      selected={selected}
      onSelect={onSelect}
    />
  );
}

function CustomerToken({
  customer,
  position,
  selected,
  onSelect,
}: {
  customer: CustomerAgent;
  position: Position;
  selected: boolean;
  onSelect: () => void;
}) {
  const colours = {
    browser: "#75a7ff",
    mission_shopper: "#c68cff",
    value_seeker: "#ff8fa3",
  };
  return (
    <AnimatedCharacter
      url={MODEL_URLS[customer.id as keyof typeof MODEL_URLS] ?? MODEL_URLS.customer_01}
      position={position}
      scale={0.68}
      accent={colours[customer.segment]}
      selected={selected}
      onSelect={onSelect}
    />
  );
}

function EquipmentUnit({
  equipment,
  state,
  selected,
  onSelect,
}: {
  equipment: Equipment;
  state: EquipmentState;
  selected: boolean;
  onSelect: () => void;
}) {
  const isColdStorage = equipment.id === "cold_storage";
  const isDisplay = equipment.id === "demo_displays";
  const colour = equipment.criticality === "protected" ? "#5aa7ff" : "#97a9a0";
  const emissive = state === "on" ? (equipment.criticality === "protected" ? "#2774bd" : "#b8fadd") : "#07110d";
  return (
    <group position={[equipment.position.x, 0, equipment.position.z]} onClick={(event) => {
      event.stopPropagation();
      onSelect();
    }}>
      <mesh position={[0, isColdStorage ? 0.8 : 0.48, 0]} castShadow receiveShadow>
        <boxGeometry args={isColdStorage ? [1.1, 1.6, 0.8] : isDisplay ? [1.5, 0.82, 0.5] : [0.75, 0.9, 0.55]} />
        <meshStandardMaterial
          color={selected ? "#d6fff0" : colour}
          emissive={emissive}
          emissiveIntensity={state === "on" ? 0.7 : 0.04}
          roughness={0.45}
        />
      </mesh>
      <mesh position={[0, 0.03, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.42, 0.48, 24]} />
        <meshBasicMaterial color={state === "on" ? "#7cf2ba" : "#55645e"} />
      </mesh>
    </group>
  );
}

function StoreGeometry({
  store,
  world,
  selection,
  setSelection,
}: {
  store: Store;
  world: WorldState;
  selection: Selection;
  setSelection: (selection: Selection) => void;
}) {
  return (
    <group onClick={() => setSelection(null)}>
      <mesh receiveShadow rotation={[-Math.PI / 2, 0, 0]} position={[-0.4, -0.04, 1]}>
        <planeGeometry args={[13.5, 10.5]} />
        <meshStandardMaterial color="#15211c" roughness={0.92} />
      </mesh>
      {store.zones.map((zone, index) => (
        <group key={zone.id} position={[zone.center.x, 0, zone.center.z]}>
          <mesh receiveShadow position={[0, 0.005, 0]}>
            <boxGeometry args={[zone.width, 0.025, zone.depth]} />
            <meshStandardMaterial
              color={index % 2 ? "#1c2c25" : "#203128"}
              transparent
              opacity={0.88}
            />
          </mesh>
          <lineSegments position={[0, 0.025, 0]}>
            <edgesGeometry args={[new THREE.BoxGeometry(zone.width, 0.03, zone.depth)]} />
            <lineBasicMaterial color="#3a5649" transparent opacity={0.75} />
          </lineSegments>
          <Html position={[-zone.width / 2 + 0.2, 0.04, -zone.depth / 2 + 0.2]} transform distanceFactor={8}>
            <span className="scene-zone-label">{zone.label}</span>
          </Html>
        </group>
      ))}

      {[[-1.8, 0.45, 0.4], [-0.2, 0.45, 0.4], [1.4, 0.45, 0.4], [-1.8, 0.45, 2.6], [-0.2, 0.45, 2.6], [1.4, 0.45, 2.6]].map((position, index) => (
        <mesh key={index} position={position as [number, number, number]} castShadow receiveShadow>
          <boxGeometry args={[1.05, 0.9, 0.42]} />
          <meshStandardMaterial color="#304239" roughness={0.72} />
        </mesh>
      ))}

      {store.equipment.map((equipment) => (
        <EquipmentUnit
          key={equipment.id}
          equipment={equipment}
          state={world.equipmentStates[equipment.id] ?? equipment.state}
          selected={selection?.kind === "equipment" && selection.id === equipment.id}
          onSelect={() => setSelection({ kind: "equipment", id: equipment.id })}
        />
      ))}
      {store.agents.map((agent) => (
        <StoreAgent
          key={agent.id}
          agent={agent}
          position={world.staffPositions[agent.id] ?? agent.position}
          selected={selection?.kind === "staff" && selection.id === agent.id}
          onSelect={() => setSelection({ kind: "staff", id: agent.id })}
        />
      ))}
      {store.customers.map((customer) => world.activeCustomers[customer.id] !== false && (
        <CustomerToken
          key={customer.id}
          customer={customer}
          position={world.customerPositions[customer.id] ?? customer.position}
          selected={selection?.kind === "customer" && selection.id === customer.id}
          onSelect={() => setSelection({ kind: "customer", id: customer.id })}
        />
      ))}
    </group>
  );
}

function selectionLabel(selection: Selection, store: Store, world: WorldState): string | null {
  if (!selection) return null;
  if (selection.kind === "staff") {
    const agent = store.agents.find((item) => item.id === selection.id);
    return agent ? `${agent.label} · ${agent.role.replaceAll("_", " ")}` : null;
  }
  if (selection.kind === "customer") {
    const customer = store.customers.find((item) => item.id === selection.id);
    return customer ? `${customer.label} · ${customer.segment.replaceAll("_", " ")}` : null;
  }
  const equipment = store.equipment.find((item) => item.id === selection.id);
  return equipment
    ? `${equipment.label} · ${world.equipmentStates[equipment.id] ?? equipment.state}`
    : null;
}

export function StoreScene({ store, world }: { store: Store; world: WorldState }) {
  const [selection, setSelection] = useState<Selection>(null);
  return (
    <div className="scene-wrap" aria-label="Interactive three-dimensional store simulation">
      <Canvas shadows camera={{ position: [11, 12, 14], fov: 38 }} dpr={[1, 1.6]}>
        <color attach="background" args={["#0d1713"]} />
        <fog attach="fog" args={["#0d1713", 18, 34]} />
        <ambientLight intensity={0.9} />
        <directionalLight position={[7, 12, 8]} intensity={2.1} castShadow shadow-mapSize={[1024, 1024]} />
        <pointLight position={[3, 5, -2]} color="#8effc7" intensity={7} distance={13} />
        <StoreGeometry
          store={store}
          world={world}
          selection={selection}
          setSelection={setSelection}
        />
        <OrbitControls
          makeDefault
          target={[-0.2, 0, 1]}
          minDistance={10}
          maxDistance={24}
          minPolarAngle={0.48}
          maxPolarAngle={1.28}
          enablePan={false}
        />
      </Canvas>
      <div className="scene-legend" aria-hidden="true">
        <span><i className="legend-staff" /> Staff agent</span>
        <span><i className="legend-customer" /> Consumer agent</span>
        <span><i className="legend-protected" /> Protected load</span>
      </div>
      <div className="scene-attribution">
        Characters by <a href="https://poly.pizza/u/J-Toastie" target="_blank" rel="noreferrer">J-Toastie</a>
        {" · "}<a href="https://creativecommons.org/licenses/by/3.0/" target="_blank" rel="noreferrer">CC BY 3.0</a>
      </div>
      {selectionLabel(selection, store, world) && (
        <div className="scene-selection">{selectionLabel(selection, store, world)}</div>
      )}
    </div>
  );
}

Object.values(MODEL_URLS).forEach((url) => useGLTF.preload(url));

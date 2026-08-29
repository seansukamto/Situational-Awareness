import { Html, OrbitControls } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef, useState } from "react";
import * as THREE from "three";

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
  const ref = useRef<THREE.Group>(null);
  const target = useMemo(() => new THREE.Vector3(position.x, 0, position.z), [position]);
  useFrame(() => ref.current?.position.lerp(target, 0.09));
  const manager = agent.role === "manager";
  return (
    <group ref={ref} position={[position.x, 0, position.z]} onClick={(event) => {
      event.stopPropagation();
      onSelect();
    }}>
      <mesh position={[0, 0.72, 0]} castShadow>
        <capsuleGeometry args={[0.2, 0.48, 6, 12]} />
        <meshStandardMaterial
          color={manager ? "#ffd36b" : "#79f2b5"}
          emissive={selected ? "#2d8b63" : "#000000"}
          emissiveIntensity={selected ? 0.8 : 0}
        />
      </mesh>
      <mesh position={[0, 1.23, 0]} castShadow>
        <sphereGeometry args={[0.22, 16, 16]} />
        <meshStandardMaterial color="#f2c7a5" />
      </mesh>
      <mesh position={[0, 0.08, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.28, selected ? 0.48 : 0.34, 24]} />
        <meshBasicMaterial color={manager ? "#ffd36b" : "#79f2b5"} transparent opacity={0.75} />
      </mesh>
    </group>
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
  const ref = useRef<THREE.Group>(null);
  const target = useMemo(() => new THREE.Vector3(position.x, 0, position.z), [position]);
  useFrame(() => ref.current?.position.lerp(target, 0.075));
  const colours = {
    browser: "#75a7ff",
    mission_shopper: "#c68cff",
    value_seeker: "#ff8fa3",
  };
  return (
    <group ref={ref} position={[position.x, 0, position.z]} onClick={(event) => {
      event.stopPropagation();
      onSelect();
    }}>
      <mesh position={[0, 0.55, 0]} castShadow>
        <capsuleGeometry args={[0.16, 0.34, 5, 10]} />
        <meshStandardMaterial
          color={colours[customer.segment]}
          emissive={selected ? colours[customer.segment] : "#000000"}
          emissiveIntensity={selected ? 0.35 : 0}
        />
      </mesh>
      <mesh position={[0, 0.96, 0]} castShadow>
        <sphereGeometry args={[0.18, 14, 14]} />
        <meshStandardMaterial color="#d8b69d" />
      </mesh>
    </group>
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
      {selectionLabel(selection, store, world) && (
        <div className="scene-selection">{selectionLabel(selection, store, world)}</div>
      )}
    </div>
  );
}

import { ContactShadows, Html, OrbitControls, useAnimations, useGLTF } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
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
  const initialPosition = useRef(position);
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

  useLayoutEffect(() => {
    movementRoot.current?.position.set(
      initialPosition.current.x,
      0,
      initialPosition.current.z,
    );
  }, []);

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
      root.position.lerp(target, 1 - Math.exp(-4.2 * delta));
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

const PRODUCT_COLOURS = ["#dce8df", "#7fd4a2", "#d4a46f", "#7ba6a0", "#e6c884"];

function RetailShelf({
  position,
  rotation = 0,
}: {
  position: [number, number, number];
  rotation?: number;
}) {
  return (
    <group position={position} rotation={[0, rotation, 0]}>
      <mesh position={[0, 0.05, 0]} castShadow receiveShadow>
        <boxGeometry args={[1.24, 0.1, 0.46]} />
        <meshStandardMaterial color="#263a31" roughness={0.66} metalness={0.12} />
      </mesh>
      {[-0.57, 0.57].map((x) => (
        <mesh key={x} position={[x, 0.52, 0]} castShadow>
          <boxGeometry args={[0.045, 0.94, 0.42]} />
          <meshStandardMaterial color="#4b6256" roughness={0.58} metalness={0.35} />
        </mesh>
      ))}
      {[0.18, 0.48, 0.78].map((y) => (
        <mesh key={y} position={[0, y, 0]} castShadow receiveShadow>
          <boxGeometry args={[1.16, 0.055, 0.44]} />
          <meshStandardMaterial color="#a88761" roughness={0.72} />
        </mesh>
      ))}
      {Array.from({ length: 12 }, (_, index) => {
        const row = Math.floor(index / 4);
        const column = index % 4;
        const height = 0.13 + (index % 3) * 0.025;
        return (
          <mesh
            key={index}
            position={[(column - 1.5) * 0.25, 0.225 + row * 0.3 + height / 2, 0]}
            castShadow
          >
            <boxGeometry args={[0.16, height, 0.22]} />
            <meshStandardMaterial color={PRODUCT_COLOURS[index % PRODUCT_COLOURS.length]} roughness={0.6} />
          </mesh>
        );
      })}
    </group>
  );
}

function Planter({ position }: { position: [number, number, number] }) {
  return (
    <group position={position}>
      <mesh position={[0, 0.22, 0]} castShadow>
        <cylinderGeometry args={[0.28, 0.22, 0.44, 16]} />
        <meshStandardMaterial color="#a47b55" roughness={0.82} />
      </mesh>
      {[
        [-0.12, 0.62, 0, 0.38],
        [0.12, 0.72, 0.04, -0.35],
        [0, 0.86, -0.08, 0.08],
      ].map(([x, y, z, rotation], index) => (
        <mesh key={index} position={[x, y, z]} rotation={[0, 0, rotation]} castShadow>
          <sphereGeometry args={[0.2, 12, 8]} />
          <meshStandardMaterial color={index === 1 ? "#4d8767" : "#67a77d"} roughness={0.72} />
        </mesh>
      ))}
    </group>
  );
}

function QueueRail({ position }: { position: [number, number, number] }) {
  return (
    <group position={position}>
      {[-0.65, 0.65].map((x) => (
        <group key={x} position={[x, 0, 0]}>
          <mesh position={[0, 0.43, 0]} castShadow>
            <cylinderGeometry args={[0.035, 0.045, 0.86, 12]} />
            <meshStandardMaterial color="#61756a" metalness={0.72} roughness={0.28} />
          </mesh>
          <mesh position={[0, 0.02, 0]}>
            <cylinderGeometry args={[0.17, 0.17, 0.04, 16]} />
            <meshStandardMaterial color="#26362f" metalness={0.45} />
          </mesh>
        </group>
      ))}
      <mesh position={[0, 0.74, 0]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.025, 0.025, 1.3, 10]} />
        <meshStandardMaterial color="#6fe1a4" emissive="#1f6e49" emissiveIntensity={0.65} />
      </mesh>
    </group>
  );
}

function ArchitecturalShell({ store }: { store: Store }) {
  return (
    <group>
      <mesh position={[-0.5, -0.16, 1]} receiveShadow>
        <boxGeometry args={[12.7, 0.3, 9.6]} />
        <meshStandardMaterial color="#0b120f" roughness={0.94} />
      </mesh>
      <mesh position={[-0.5, 0.005, 1]} receiveShadow>
        <boxGeometry args={[12.3, 0.035, 9.2]} />
        <meshStandardMaterial color="#18251f" roughness={0.78} metalness={0.06} />
      </mesh>
      <gridHelper
        args={[12, 24, "#3d5a4c", "#26382f"]}
        position={[-0.5, 0.028, 1]}
      />

      <mesh position={[-6.16, 1.42, 1]} castShadow receiveShadow>
        <boxGeometry args={[0.18, 2.84, 9.25]} />
        <meshStandardMaterial color="#26372f" roughness={0.82} />
      </mesh>
      <mesh position={[-6.02, 0.13, 1]}>
        <boxGeometry args={[0.12, 0.18, 9.05]} />
        <meshStandardMaterial color="#77d6a0" emissive="#1d6945" emissiveIntensity={0.52} />
      </mesh>

      {[-4.45, 2.75].map((x, index) => (
        <mesh key={x} position={[x, 1.43, -3.56]} receiveShadow>
          <boxGeometry args={[index === 0 ? 3.15 : 4.15, 2.62, 0.055]} />
          <meshPhysicalMaterial
            color="#93c7b1"
            transparent
            opacity={0.16}
            roughness={0.08}
            metalness={0.08}
            transmission={0.35}
            depthWrite={false}
          />
        </mesh>
      ))}
      {[-6.05, -2.85, 0.65, 4.84].map((x) => (
        <mesh key={x} position={[x, 1.45, -3.55]} castShadow>
          <boxGeometry args={[0.075, 2.9, 0.1]} />
          <meshStandardMaterial color="#5c7568" metalness={0.52} roughness={0.28} />
        </mesh>
      ))}
      <mesh position={[-0.5, 2.94, -3.57]} castShadow>
        <boxGeometry args={[11.2, 0.58, 0.18]} />
        <meshStandardMaterial color="#14231c" roughness={0.52} metalness={0.25} />
      </mesh>
      <mesh position={[-0.5, 2.66, -3.66]}>
        <boxGeometry args={[11.0, 0.025, 0.05]} />
        <meshStandardMaterial color="#76ecaa" emissive="#53d58e" emissiveIntensity={2.6} />
      </mesh>
      <Html position={[-0.4, 2.98, -3.7]} transform distanceFactor={6.5}>
        <div className="storefront-sign"><b>SA</b><span>SITUATIONAL AWARENESS</span></div>
      </Html>
      <Html position={[-1.12, 2.18, -3.61]} transform distanceFactor={7.5}>
        <div className="entry-sign"><i /> ENTER</div>
      </Html>

      {Array.from({ length: 9 }, (_, index) => (
        <mesh key={index} position={[5.08, 1.25, -2.55 + index * 0.88]} castShadow>
          <boxGeometry args={[0.1, 2.5, 0.075]} />
          <meshStandardMaterial color="#40564b" roughness={0.55} metalness={0.2} />
        </mesh>
      ))}
      <mesh position={[5.04, 0.16, 1]}>
        <boxGeometry args={[0.14, 0.28, 7.9]} />
        <meshStandardMaterial color="#7c9e8d" emissive="#224e38" emissiveIntensity={0.45} />
      </mesh>

      <mesh position={[-3.02, 1.1, 5.45]} castShadow receiveShadow>
        <boxGeometry args={[5.9, 2.2, 0.15]} />
        <meshStandardMaterial color="#203129" roughness={0.84} />
      </mesh>
      <mesh position={[-3.02, 0.17, 5.34]}>
        <boxGeometry args={[5.55, 0.16, 0.08]} />
        <meshStandardMaterial color="#6dd59d" emissive="#1d6846" emissiveIntensity={0.4} />
      </mesh>

      {store.zones.map((zone, index) => (
        <group key={zone.id} position={[zone.center.x, 0, zone.center.z]}>
          <mesh receiveShadow position={[0, 0.018, 0]}>
            <boxGeometry args={[zone.width - 0.08, 0.018, zone.depth - 0.08]} />
            <meshStandardMaterial
              color={index % 2 ? "#1a2922" : "#1d2d25"}
              transparent
              opacity={0.6}
              roughness={0.9}
            />
          </mesh>
          <lineSegments position={[0, 0.04, 0]}>
            <edgesGeometry args={[new THREE.BoxGeometry(zone.width, 0.03, zone.depth)]} />
            <lineBasicMaterial color="#4d6b5c" transparent opacity={0.34} />
          </lineSegments>
          <Html position={[-zone.width / 2 + 0.24, 0.05, -zone.depth / 2 + 0.24]} transform distanceFactor={8}>
            <span className="scene-zone-label">{zone.label}</span>
          </Html>
        </group>
      ))}

      <Planter position={[-1.72, 0, -3.03]} />
      <Planter position={[4.5, 0, -2.92]} />
      <QueueRail position={[-4.6, 0, -0.75]} />
      <QueueRail position={[-3.1, 0, -0.75]} />
    </group>
  );
}

function EquipmentFixture({
  equipment,
  state,
  selected,
}: {
  equipment: Equipment;
  state: EquipmentState;
  selected: boolean;
}) {
  const active = state === "on";
  const statusColour = active ? "#78efac" : "#52635a";
  const highlight = selected ? "#dcfff0" : "#81978c";

  if (equipment.id === "cold_storage") {
    return (
      <group>
        <mesh position={[0, 0.92, 0]} castShadow receiveShadow>
          <boxGeometry args={[1.28, 1.84, 0.86]} />
          <meshStandardMaterial color={selected ? "#d9f5ff" : "#b9c9c4"} metalness={0.32} roughness={0.36} />
        </mesh>
        {[-0.31, 0.31].map((x) => (
          <mesh key={x} position={[x, 0.94, -0.437]}>
            <boxGeometry args={[0.55, 1.52, 0.025]} />
            <meshPhysicalMaterial color="#3d7284" transparent opacity={0.58} roughness={0.1} transmission={0.25} />
          </mesh>
        ))}
        <mesh position={[0, 1.72, -0.46]}>
          <boxGeometry args={[1.08, 0.08, 0.04]} />
          <meshStandardMaterial color="#72bfff" emissive="#2b84cc" emissiveIntensity={active ? 2.3 : 0.25} />
        </mesh>
        <Html position={[0, 2.02, 0]} center transform distanceFactor={8}>
          <span className="equipment-flag protected">Protected load</span>
        </Html>
      </group>
    );
  }

  if (equipment.id === "checkout_pos") {
    return (
      <group position={[0, 0, -0.44]}>
        <mesh position={[0, 0.46, 0]} castShadow receiveShadow>
          <boxGeometry args={[1.72, 0.82, 0.72]} />
          <meshStandardMaterial color={selected ? "#dff8ed" : "#52665c"} roughness={0.5} />
        </mesh>
        <mesh position={[0, 0.9, 0]} castShadow>
          <boxGeometry args={[1.82, 0.08, 0.82]} />
          <meshStandardMaterial color="#b6946c" roughness={0.62} />
        </mesh>
        <mesh position={[0.35, 1.22, 0]} rotation={[-0.15, 0, 0]} castShadow>
          <boxGeometry args={[0.52, 0.42, 0.08]} />
          <meshStandardMaterial color="#18231e" emissive={active ? "#57d992" : "#101914"} emissiveIntensity={active ? 1.5 : 0.1} />
        </mesh>
        <mesh position={[-0.48, 0.98, 0]}>
          <boxGeometry args={[0.34, 0.09, 0.28]} />
          <meshStandardMaterial color="#202d27" metalness={0.25} />
        </mesh>
      </group>
    );
  }

  if (equipment.id === "stockroom_lights") {
    return (
      <group>
        <mesh position={[0, 2.35, 0]} castShadow>
          <boxGeometry args={[2.6, 0.1, 0.22]} />
          <meshStandardMaterial color="#34483e" metalness={0.38} roughness={0.44} />
        </mesh>
        {[-0.86, 0, 0.86].map((x) => (
          <mesh key={x} position={[x, 2.27, 0]}>
            <boxGeometry args={[0.54, 0.035, 0.13]} />
            <meshStandardMaterial
              color={statusColour}
              emissive={active ? "#c8ffdb" : "#101713"}
              emissiveIntensity={active ? 2.4 : 0.06}
            />
          </mesh>
        ))}
        {active && (
          <pointLight position={[0, 2.1, 0]} color="#d7ffe5" intensity={5.5} distance={5.5} />
        )}
      </group>
    );
  }

  if (equipment.id === "demo_displays") {
    return (
      <group>
        <mesh position={[0, 0.34, 0]} castShadow receiveShadow>
          <cylinderGeometry args={[0.88, 0.98, 0.66, 20]} />
          <meshStandardMaterial color={selected ? "#e2fff1" : "#40554a"} roughness={0.48} />
        </mesh>
        <mesh position={[0, 0.7, 0]}>
          <cylinderGeometry args={[0.9, 0.9, 0.08, 20]} />
          <meshStandardMaterial color="#aa8b66" roughness={0.56} />
        </mesh>
        {[-0.48, 0, 0.48].map((x, index) => (
          <group key={x} position={[x, 0.91, index % 2 ? 0.05 : -0.02]} rotation={[0.08, index === 1 ? 0 : index === 0 ? -0.22 : 0.22, 0]}>
            <mesh castShadow>
              <boxGeometry args={[0.34, 0.44, 0.055]} />
              <meshStandardMaterial color="#15231d" emissive={active ? "#70e9aa" : "#0b130f"} emissiveIntensity={active ? 1.2 : 0.08} />
            </mesh>
          </group>
        ))}
      </group>
    );
  }

  if (equipment.id === "display_wall_lights") {
    return (
      <group>
        <mesh position={[0.64, 1.18, 0]} castShadow receiveShadow>
          <boxGeometry args={[0.22, 2.36, 2.3]} />
          <meshStandardMaterial color={selected ? "#dffff0" : "#33483e"} roughness={0.64} />
        </mesh>
        {[-0.72, 0, 0.72].map((z) => (
          <mesh key={z} position={[0.5, 1.38, z]}>
            <boxGeometry args={[0.06, 1.56, 0.08]} />
            <meshStandardMaterial color={statusColour} emissive={active ? "#65e4a0" : "#18241e"} emissiveIntensity={active ? 2.1 : 0.05} />
          </mesh>
        ))}
        {active && <pointLight position={[0.05, 1.65, 0]} color="#b7ffcf" intensity={4.5} distance={4.5} />}
      </group>
    );
  }

  return (
    <group>
      <mesh position={[0, 0.66, 0]} castShadow>
        <boxGeometry args={[0.52, 1.32, 0.42]} />
        <meshStandardMaterial color={highlight} roughness={0.48} metalness={0.18} />
      </mesh>
      <mesh position={[0, 0.86, -0.23]}>
        <boxGeometry args={[0.28, 0.38, 0.04]} />
        <meshStandardMaterial color="#16231d" emissive={active ? "#68e8a2" : "#101713"} emissiveIntensity={active ? 1.4 : 0.05} />
      </mesh>
      {active && <pointLight position={[0, 2.6, 0]} color="#d5ffe4" intensity={5} distance={5.5} />}
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
  const statusColour = state === "on"
    ? equipment.criticality === "protected" ? "#62b7ff" : "#78efac"
    : "#52635a";
  return (
    <group position={[equipment.position.x, 0, equipment.position.z]} onClick={(event) => {
      event.stopPropagation();
      onSelect();
    }}>
      <EquipmentFixture equipment={equipment} state={state} selected={selected} />
      <mesh position={[0, 0.03, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.43, selected ? 0.58 : 0.49, 28]} />
        <meshBasicMaterial color={statusColour} transparent opacity={selected ? 0.95 : 0.58} />
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
      <ArchitecturalShell store={store} />
      <RetailShelf position={[-1.9, 0, 0.2]} />
      <RetailShelf position={[-0.25, 0, 0.2]} />
      <RetailShelf position={[-1.9, 0, 2.15]} />
      <RetailShelf position={[-0.25, 0, 2.15]} />

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
      <Canvas
        shadows
        camera={{ position: [12.4, 11.4, 13.2], fov: 36 }}
        dpr={[1, 1.75]}
        gl={{ antialias: true, toneMapping: THREE.ACESFilmicToneMapping }}
        onCreated={({ gl }) => { gl.toneMappingExposure = 1.12; }}
      >
        <color attach="background" args={["#08110d"]} />
        <fog attach="fog" args={["#08110d", 17, 31]} />
        <hemisphereLight args={["#d7ffe6", "#07100b", 1.25]} />
        <ambientLight intensity={0.32} />
        <directionalLight
          position={[7, 13, 8]}
          intensity={2.8}
          castShadow
          shadow-mapSize={[2048, 2048]}
          shadow-bias={-0.00025}
          shadow-camera-left={-9}
          shadow-camera-right={9}
          shadow-camera-top={9}
          shadow-camera-bottom={-9}
        />
        <spotLight
          position={[-2, 9, 4]}
          color="#e3ffed"
          intensity={28}
          distance={22}
          angle={0.78}
          penumbra={0.72}
          castShadow
        />
        <pointLight position={[3, 5, -2]} color="#8effc7" intensity={8} distance={13} />
        <pointLight position={[-5.4, 2.4, -2.7]} color="#e9c995" intensity={3.2} distance={6} />
        <StoreGeometry
          store={store}
          world={world}
          selection={selection}
          setSelection={setSelection}
        />
        <ContactShadows
          position={[-0.5, 0.045, 1]}
          scale={14}
          opacity={0.5}
          blur={2.5}
          far={5}
          color="#000000"
        />
        <OrbitControls
          makeDefault
          target={[-0.35, 0.55, 0.85]}
          minDistance={10.5}
          maxDistance={23}
          minPolarAngle={0.52}
          maxPolarAngle={1.2}
          enablePan={false}
        />
      </Canvas>
      <div className="scene-vignette" aria-hidden="true" />
      <div className="scene-brandplate" aria-hidden="true">
        <span><i /> Live digital twin</span>
        <strong>{store.name.replace(" — Demo", "")} · {store.floor_area_m2} m²</strong>
      </div>
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

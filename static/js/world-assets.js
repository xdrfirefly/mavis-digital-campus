export const assets = {
  buildings: {
    manor: '/static/assets/buildings/mavis-manor/map-sprite.png',
    barn: '/static/assets/buildings/coopenheimer-barn/map-sprite.png',
    library: '/static/assets/buildings/library-of-mavis/map-sprite.png',
  },
  agents: {
    chief: '/static/assets/agents/stella-sprite.png',
    programs: '/static/assets/agents/percy-sprite.png',
    research: '/static/assets/agents/rose-sprite.png',
    caretaker: '/static/assets/agents/stewart-sprite.png',
    grants: '/static/assets/agents/vernadette-sprite.png',
    operations: '/static/assets/agents/poe-sprite.png',
  },
  vegetation: {
    red: '/static/assets/vegetation/fruit-tree-red.svg',
    gold: '/static/assets/vegetation/fruit-tree-gold.svg',
    green: '/static/assets/vegetation/tree-green.svg',
    shrub: '/static/assets/vegetation/shrub.svg',
    flowers: '/static/assets/vegetation/flowers.svg',
  },
  props: {
    bridge: '/static/assets/props/bridge.svg',
    bench: '/static/assets/props/bench.svg',
    lamp: '/static/assets/props/lamp.svg',
    sign: '/static/assets/props/sign.svg',
  },
};

// Separate placement data keeps the Fruit Forest expandable without repainting the map.
export const forestPlacements = [
  ['red',7,20,1.04],['gold',17,5,1.12],['green',28,22,.96],['red',39,7,1.07],['gold',51,18,1.02],
  ['green',63,2,1.10],['red',75,17,.96],['gold',84,32,.9],['green',2,48,.9],['gold',13,42,.96],
  ['red',25,50,.88],['green',37,42,1.0],['gold',49,50,.92],['red',60,43,.98],['green',71,50,.86],
  ['red',16,70,.8],['green',31,69,.84],['gold',47,72,.82],['red',64,68,.8],['green',79,65,.78],
];

export const worldProps = [
  {type:'bench', x:12.5, y:74, rotate:-7},
  {type:'bench', x:56, y:45.5, rotate:3},
  {type:'lamp', x:67, y:57, rotate:0},
  {type:'lamp', x:47.5, y:48, rotate:0},
  {type:'flowers', x:16, y:84, rotate:-3},
  {type:'flowers', x:72, y:85, rotate:2},
  {type:'flowers', x:72, y:31, rotate:-3},
  {type:'shrub', x:27, y:83, rotate:0},
  {type:'shrub', x:82, y:80, rotate:0},
];

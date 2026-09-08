export const worldConfig = {
  size: { width: 1400, height: 900 },
  locations: {
    pond: { x: 20, y: 18, label: 'Pond' },
    barn: { x: 79, y: 22, label: 'Coopenheimer Barn' },
    fruit_forest: { x: 35, y: 50, label: 'Fruit Forest' },
    manor: { x: 18, y: 73, label: 'Mavis Manor' },
    library: { x: 79, y: 73, label: 'Library of Mavis' },
  },
  // Reserved empty areas are intentional growth space for future campus additions.
  expansionZones: [
    { id:'north_center', x:52, y:16, width:18, height:18 },
    { id:'east_center', x:88, y:49, width:15, height:24 },
    { id:'south_center', x:50, y:84, width:19, height:12 },
  ],
  routeNodes: {
    manor: {x:18, y:73},
    manor_gate: {x:28, y:70},
    bridge_manor: {x:48, y:47},
    forest_south: {x:39, y:58},
    forest: {x:35, y:50},
    bridge_pond: {x:37, y:34},
    pond_gate: {x:27, y:25},
    pond: {x:20, y:18},
    forest_east: {x:44, y:48},
    campus_cross: {x:54, y:47},
    barn_gate: {x:68, y:34},
    barn: {x:79, y:22},
    bridge_library: {x:55, y:70},
    library_gate: {x:69, y:70},
    library: {x:79, y:73}
  },
  routeEdges: {
    manor:['manor_gate'], manor_gate:['manor','bridge_manor'], bridge_manor:['manor_gate','forest_south'], forest_south:['bridge_manor','forest'], forest:['forest_south','bridge_pond','forest_east'],
    bridge_pond:['forest','pond_gate'], pond_gate:['bridge_pond','pond'], pond:['pond_gate'],
    forest_east:['forest','campus_cross'], campus_cross:['forest_east','barn_gate','bridge_library'],
    barn_gate:['campus_cross','barn'], barn:['barn_gate'],
    bridge_library:['campus_cross','library_gate'], library_gate:['bridge_library','library'], library:['library_gate']
  },
  buildingNode: { manor:'manor', barn:'barn', library:'library', fruit_forest:'forest' },
};

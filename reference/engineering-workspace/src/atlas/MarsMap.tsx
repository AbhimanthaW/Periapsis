import { useEffect, useImperativeHandle, useRef, useState } from 'react'
import type { Ref } from 'react'
import { Crosshair, Minus, Plus, RotateCcw } from 'lucide-react'
import Map from 'ol/Map.js'
import View from 'ol/View.js'
import Projection from 'ol/proj/Projection.js'
import { addProjection } from 'ol/proj.js'
import { defaults as controls } from 'ol/control/defaults.js'
import { defaults as interactions } from 'ol/interaction/defaults.js'
import TileLayer from 'ol/layer/Tile.js'
import ImageLayer from 'ol/layer/Image.js'
import VectorLayer from 'ol/layer/Vector.js'
import XYZ from 'ol/source/XYZ.js'
import ImageStatic from 'ol/source/ImageStatic.js'
import VectorSource from 'ol/source/Vector.js'
import TileGrid from 'ol/tilegrid/TileGrid.js'
import Feature from 'ol/Feature.js'
import Point from 'ol/geom/Point.js'
import LineString from 'ol/geom/LineString.js'
import GeoJSON from 'ol/format/GeoJSON.js'
import Style from 'ol/style/Style.js'
import CircleStyle from 'ol/style/Circle.js'
import Fill from 'ol/style/Fill.js'
import Stroke from 'ol/style/Stroke.js'
import Text from 'ol/style/Text.js'
import 'ol/ol.css'
import jezeroUrl from '../../../../web/src/mission/assets/jezero.webp'
import { assets, assessmentFor, atlasAsset, coordinatesLabel, featureColor, globalExtent, normalizeLongitude, ratingColor } from './data'
import type { MapMode, Profile, Region } from './data'

const projection = new Projection({ code:'RETURN-WINDOW:MARS-PLANETOCENTRIC-EAST', units:'degrees', extent:globalExtent, global:true, metersPerUnit:3396190*Math.PI/180 })
addProjection(projection)
const grid = new TileGrid({ extent:globalExtent, origin:[-180,90], resolutions:[360/512,360/1024,360/2048], tileSize:256 })
const drawGrid = new Style({stroke:new Stroke({color:'rgba(229,232,237,.21)',width:1,lineDash:[3,7]})})
const formatter = new GeoJSON()
const initialResolution = 360/512

export interface Camera { center:[number,number]; zoom:number }
export interface MapControls { locate:(region:Region)=>void; planet:()=>void; detail:()=>void }
type Props = {
  ref:Ref<MapControls>; camera?:Camera; saveCamera:(camera:Camera)=>void;
  regions:Region[]; selected:string|null; select:(id:string)=>void; mode:MapMode; profile:Profile;
  basemap:'viking'|'mola'; showMarkers:boolean; showLabels:boolean; showGrid:boolean; showDetail:boolean;
}
function gridFeatures() {
  const features: Feature<LineString>[] = []
  for (let x=-180;x<180;x+=30) features.push(new Feature(new LineString([[x,-90],[x,90]])))
  for (let y=-60;y<=60;y+=30) features.push(new Feature(new LineString([[-180,y],[180,y]])))
  return features
}
const tileSource = (id:'viking'|'mola')=>new XYZ({
  projection,tileGrid:grid,wrapX:true,
  tileUrlFunction:coordinate=>atlasAsset(`${id}/${coordinate[0]}/${coordinate[1]}/${coordinate[2]}.webp`),
})
export function MarsMap({ref,...props}:Props) {
  const element=useRef<HTMLDivElement>(null)
  const map=useRef<Map|null>(null)
  const callbacks=useRef(props)
  callbacks.current=props
  const layers=useRef<{viking:TileLayer<XYZ>; mola:TileLayer<XYZ>; grid:VectorLayer; detail:ImageLayer<ImageStatic>; markers:VectorLayer}|null>(null)
  const [coords,setCoords]=useState([0,0])
  const [mapScale,setMapScale]=useState({km:0,px:0})
  const [overlap,setOverlap]=useState<{ ids:string[]; pixel:number[] }|null>(null)
  const [tileError,setTileError]=useState(false)
  const markers=useRef(new VectorSource({wrapX:true}))
  const fit=()=>{
    const m=map.current
    if (!m?.getSize()) return
    m.getView().fit(globalExtent,{size:m.getSize(),padding:[34,26,40,26]})
  }
  useImperativeHandle(ref,()=>({
    locate(region) {
      const view=map.current?.getView()
      if (!view) return
      const center=view.getCenter() ?? [0,0]
      const lon=region.geography.center[0]+360*Math.round((center[0]-region.geography.center[0])/360)
      view.animate({center:[lon,region.geography.center[1]],zoom:Math.max(4,Math.min(view.getZoom() ?? 4,9)),duration:240})
    },
    planet:fit,
    detail(){map.current?.getView().fit(assets.jezero.extent,{padding:[40,40,40,40],duration:280,maxZoom:12})},
  }))
  useEffect(()=>{
    if (!element.current) return
    const current=callbacks.current
    const viking=new TileLayer({source:tileSource('viking'),visible:current.basemap==='viking'})
    const mola=new TileLayer({source:tileSource('mola'),visible:current.basemap==='mola'})
    const detail=new ImageLayer({
      source:new ImageStatic({url:jezeroUrl,projection,imageExtent:assets.jezero.extent}),
      visible:current.showDetail,maxResolution:.012,
    })
    const gridLayer=new VectorLayer({source:new VectorSource({features:gridFeatures(),wrapX:true}),style:drawGrid,visible:current.showGrid})
    const markerLayer=new VectorLayer({source:markers.current,declutter:true})
    const view=new View({
      projection,center:current.camera?.center ?? [0,0],zoom:current.camera?.zoom ?? 1,
      minZoom:0,maxZoom:14,maxResolution:initialResolution*2,multiWorld:true,enableRotation:false,
      extent:[-1800,-90,1800,90],constrainOnlyCenter:true,
    })
    const instance=new Map({
      target:element.current,layers:[viking,mola,detail,gridLayer,markerLayer],view,
      controls:controls({attribution:false,zoom:false,rotate:false}),
      interactions:interactions({onFocusOnly:false,altShiftDragRotate:false,pinchRotate:false}),
    })
    map.current=instance
    layers.current={viking,mola,grid:gridLayer,detail,markers:markerLayer}
    viking.getSource()?.on('tileloaderror',()=>setTileError(true))
    mola.getSource()?.on('tileloaderror',()=>setTileError(true))
    detail.getSource()?.on('imageloaderror',()=>setTileError(true))
    const onMove=()=>{
      const center=view.getCenter()
      if (!center) return
      const lat=Math.max(-90,Math.min(90,center[1]))
      callbacks.current.saveCamera({center:[normalizeLongitude(center[0]),lat],zoom:view.getZoom() ?? 0})
      setCoords([center[0],lat])
      if (Math.abs(lat)>=89.5) {
        setMapScale({km:0,px:0})
        return
      }
      const kmPerPixel=(view.getResolution() ?? initialResolution)*3396.19*Math.PI/180*Math.max(0,Math.cos(lat*Math.PI/180))
      const target=kmPerPixel*96
      const step=10**Math.floor(Math.log10(target))
      const km=[5,2,1].map(n=>n*step).find(n=>n<=target) ?? step
      setMapScale({km,px:km/kmPerPixel})
    }
    instance.on('pointermove',event=>{
      if (!event.dragging) {
        setCoords(event.coordinate)
        const hit=instance.hasFeatureAtPixel(event.pixel,{layerFilter:layer=>layer===markerLayer,hitTolerance:5})
        if (element.current) element.current.style.cursor=hit?'pointer':'grab'
      }
    })
    instance.on('singleclick',event=>{
      const hits=new Set<string>()
      instance.forEachFeatureAtPixel(event.pixel,feature=>{
        const id=feature.get('regionId')
        if (id) hits.add(id)
      },{hitTolerance:7,layerFilter:layer=>layer===markerLayer})
      if (hits.size===1) callbacks.current.select([...hits][0])
      setOverlap(hits.size>1?{ids:[...hits].sort(),pixel:event.pixel}:null)
    })
    instance.on('movestart',()=>setOverlap(null))
    instance.on('moveend',onMove)
    const resize=new ResizeObserver(()=>instance.updateSize())
    resize.observe(element.current)
    const frame=requestAnimationFrame(()=>{instance.updateSize();if (!current.camera) fit();onMove()})
    return ()=>{cancelAnimationFrame(frame);resize.disconnect();instance.setTarget(undefined);instance.dispose();map.current=null;layers.current=null}
  },[])
  useEffect(()=>{
    const layer=layers.current
    if (!layer) return
    layer.viking.setVisible(props.basemap==='viking')
    layer.mola.setVisible(props.basemap==='mola')
    layer.grid.setVisible(props.showGrid)
    layer.detail.setVisible(props.showDetail)
    layer.markers.setVisible(props.showMarkers)
    setOverlap(null)
  },[props.basemap,props.showGrid,props.showDetail,props.showMarkers])
  useEffect(()=>{
    const source=markers.current
    source.clear()
    source.addFeatures(props.regions.map(region=>{
      const geometry=region.geography.shape ? formatter.readGeometry(region.geography.shape,{dataProjection:projection,featureProjection:projection}) ?? new Point(region.geography.center) : new Point(region.geography.center)
      return new Feature({geometry,regionId:region.id})
    }))
  },[props.regions])
  useEffect(()=>{
    const layer=layers.current?.markers
    if (!layer) return
    const styles=new globalThis.Map<string,Style>()
    const lookup=new globalThis.Map(props.regions.map(region=>[region.id,region]))
    layer.setStyle((feature,resolution)=>{
      const region=lookup.get(feature.get('regionId'))
      if (!region) return
      const active=region.id===props.selected
      const showLabel=props.showLabels && (active || resolution<.22 || ['01','03','06','08','15','22','33','43','44'].includes(region.id))
      const key=region.id+(showLabel?'label':'')
      const cached=styles.get(key)
      if (cached) return cached
      const assessment=props.mode==='feature'?null:assessmentFor(region,props.mode,props.profile)
      const color=props.mode==='feature'?featureColor(region.featureType):ratingColor(props.mode,assessment?.rating ?? null)
      const filled=props.mode==='feature'||Boolean(assessment?.rating)
      const stroke=new Stroke({color:active?'#f9e7cc':color,width:active?2.5:1.6})
      const style=new Style({
        zIndex:active?10:filled?3:1, stroke, fill:new Fill({color:color+'30'}),
        image:new CircleStyle({radius:active?9:6,fill:new Fill({color:filled?color:'#222633'}),stroke:new Stroke({color:active?'#f9e7cc':filled?'#1c1b20':color,width:active?2.5:1.6}),declutterMode:'none'}),
        text:showLabel?new Text({text:region.name,font:`${active?'600':'500'} 12px system-ui`,offsetY:region.geography.center[1]>75?15:-15,fill:new Fill({color:'#fff0db'}),stroke:new Stroke({color:'#16141a',width:3.5}),declutterMode:active?'none':'declutter'}):undefined,
      })
      styles.set(key,style)
      return style
    })
  },[props.mode,props.profile,props.selected,props.regions,props.showLabels])
  const zoom=(amount:number)=>{
    const view=map.current?.getView()
    if (view) view.animate({zoom:(view.getZoom() ?? 0)+amount,duration:140})
  }
  return <div className="mars-map">
    <div className="mars-surface" ref={element} tabIndex={0} aria-label="Interactive Mars map. Use arrow keys to pan and plus or minus to zoom."/>
    {tileError&&<div className="atlas-map-error" role="status">A local raster could not load. Region research is still available.</div>}
    <div className="mars-controls" aria-label="Map controls">
      <button className="icon-button" title="Zoom in" aria-label="Zoom in" onClick={()=>zoom(1)}><Plus size={17}/></button>
      <button className="icon-button" title="Zoom out" aria-label="Zoom out" onClick={()=>zoom(-1)}><Minus size={17}/></button>
      <button className="icon-button" title="Fit to Mars" aria-label="Fit to Mars" onClick={fit}><RotateCcw size={16}/></button>
    </div>
    {overlap&&<div className="atlas-overlap" style={{left:`clamp(8px, ${overlap.pixel[0]}px, 100% - 205px)`,top:`clamp(8px, ${overlap.pixel[1]}px, 100% - 115px)`}} aria-label="Overlapping regions">
      <strong>Choose a feature</strong>
      {overlap.ids.map(id=><button key={id} onClick={()=>{props.select(id);setOverlap(null)}}>{id} · {props.regions.find(region=>region.id===id)?.name}</button>)}
    </div>}
    <div className="mars-bottom"><span><Crosshair size={13}/> {coordinatesLabel(coords)}</span>
      {mapScale.km>0 && Number.isFinite(mapScale.px) && <span className="mars-scale"><i style={{width:mapScale.px}}/>≈ {mapScale.km>=1?`${mapScale.km} km`:`${Math.round(mapScale.km*1000)} m`}</span>}
      <a href={assets[props.basemap].source} target="_blank" rel="noreferrer">{assets[props.basemap].credit}</a>
    </div>
  </div>
}

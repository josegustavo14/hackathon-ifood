import React from 'react'

export default function RecipeArt({ small = false }) {
  return <div className={`recipe-art ${small ? 'small' : ''}`} aria-hidden="true">
    <div className="art-orbit orbit-one"/><div className="art-orbit orbit-two"/>
    <span className="art-leaf leaf-one"/><span className="art-leaf leaf-two"/>
    <div className="plate"><div className="lasagna"><span/><span/><span/><i/><i/><i/><b/><b/></div></div>
    <span className="art-tomato tomato-one"/><span className="art-tomato tomato-two"/>
    {!small && <span className="art-caption"><span>feito em casa</span><strong>fica ainda melhor.</strong></span>}
  </div>
}

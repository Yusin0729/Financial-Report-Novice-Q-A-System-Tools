/* 五階段共用的檔案樹與選取狀態；資料夾勾選包含未顯示的全部子檔案。 */
(function(root) {
  function visible(items, selected, query, filter) {
    const q=query.toLowerCase();
    return items.filter(x=>x.id.toLowerCase().includes(q)&&
      (filter==='all'||(filter==='selected')===selected.has(x.id)));
  }
  function tree(items) {
    const root={folders:new Map(),files:[]};
    for(const item of items) {
      const parts=item.id.split('/');let node=root,path='';
      for(const name of parts.slice(0,-1)) {
        path=path?path+'/'+name:name;
        if(!node.folders.has(name))node.folders.set(name,{name,path,folders:new Map(),files:[]});
        node=node.folders.get(name);
      }
      node.files.push({...item,name:parts[parts.length-1]});
    }
    return root;
  }
  function descendants(items,path) {return items.filter(x=>x.id.startsWith(path+'/')).map(x=>x.id);}
  function state(ids,selected) {
    const count=ids.filter(id=>selected.has(id)).length;
    return {count,total:ids.length,checked:ids.length>0&&count===ids.length,indeterminate:count>0&&count<ids.length};
  }
  function set(ids,selected,checked) {for(const id of ids)checked?selected.add(id):selected.delete(id);}
  const api={visible,tree,descendants,state,set};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  else root.SelectionTree=api;
})(globalThis);

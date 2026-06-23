(function(){
  function getCookie(name){let cookieValue=null;if(document.cookie&&document.cookie!==''){const cookies=document.cookie.split(';');for(let i=0;i<cookies.length;i++){const cookie=cookies[i].trim();if(cookie.substring(0,name.length+1)===(name+'=')){cookieValue=decodeURIComponent(cookie.substring(name.length+1));break;}}}return cookieValue;}
  window.crmFetch = async function(url, options={}){
    const opts = Object.assign({headers:{}}, options);
    opts.headers['X-Requested-With']='XMLHttpRequest';
    if(!opts.headers['X-CSRFToken']) opts.headers['X-CSRFToken']=getCookie('csrftoken');
    const res = await fetch(url, opts);
    const contentType = res.headers.get('content-type') || '';
    const data = contentType.includes('application/json') ? await res.json() : await res.text();
    if(!res.ok){throw new Error((data && data.error) || (typeof data==='string'?data:'Request failed'));}
    return data;
  };
  window.crmToast = function(title, icon='success'){
    if(window.Swal){Swal.fire({toast:true,position:'top-end',icon,title,showConfirmButton:false,timer:2200,timerProgressBar:true});}
    else alert(title);
  };
  window.crmConfirm = async function(title, text=''){
    if(!window.Swal) return confirm(title);
    const result = await Swal.fire({title,text,icon:'question',showCancelButton:true,confirmButtonText:'Yes, continue',cancelButtonText:'Cancel',reverseButtons:true});
    return result.isConfirmed;
  };
  document.addEventListener('click', async function(e){
    const el=e.target.closest('[data-confirm]:not(form)');
    if(!el) return;
    e.preventDefault();
    const ok = await crmConfirm(el.dataset.confirm, el.dataset.confirmText || '');
    if(ok){
      const originalConfirm = el.dataset.confirm;
      delete el.dataset.confirm;
      el.click();
      el.dataset.confirm = originalConfirm;
    }
  });
  document.addEventListener('submit', async function(e){
    const form=e.target.closest('form');
    if(!form) return;
    if(form.hasAttribute('data-ajax-form')){
      e.preventDefault();
      const ok = form.dataset.confirm ? await crmConfirm(form.dataset.confirm, form.dataset.confirmText || '') : true;
      if(!ok) return;
      form.classList.add('ajax-loading');
      try{
        const data = await crmFetch(form.action || window.location.href, {method:form.method || 'POST', body:new FormData(form)});
        crmToast(data.message || 'Saved successfully', 'success');
        if(data.redirect_url){setTimeout(()=>{window.location.href=data.redirect_url;}, 500);} 
        else if(data.reload){setTimeout(()=>window.location.reload(), 500);}
      }catch(err){
        if(window.Swal) Swal.fire('Could not save', err.message, 'error'); else alert(err.message);
      }finally{form.classList.remove('ajax-loading');}
    } else if(form.dataset.confirm) {
      if(form.dataset.confirmed === 'true'){
        delete form.dataset.confirmed;
        return;
      }
      e.preventDefault();
      const ok = await crmConfirm(form.dataset.confirm, form.dataset.confirmText || '');
      if(ok){
        form.dataset.confirmed = 'true';
        if(typeof form.requestSubmit === 'function'){
          form.requestSubmit(e.submitter || undefined);
        }else{
          form.submit();
        }
      }
    }
  });
  document.addEventListener('click', function(e){
    const btn=e.target.closest('[data-tab-target]'); if(!btn) return;
    const group=btn.dataset.tabGroup || 'default';
    document.querySelectorAll(`[data-tab-group="${group}"]`).forEach(x=>x.classList.remove('active'));
    document.querySelectorAll(`[data-tab-panel-group="${group}"]`).forEach(x=>x.classList.remove('active'));
    btn.classList.add('active'); document.querySelector(btn.dataset.tabTarget)?.classList.add('active');
  });
  document.addEventListener('click', function(e){
    const btn=e.target.closest('[data-add-repeater]'); if(!btn) return;
    const target=document.querySelector(btn.dataset.addRepeater); const tpl=document.querySelector(btn.dataset.template);
    if(!target || !tpl) return;
    const index = target.children.length;
    const html = tpl.innerHTML.replaceAll('__INDEX__', index).replaceAll('__DISPLAY_INDEX__', index+1);
    const wrapper=document.createElement('div'); wrapper.innerHTML=html.trim(); target.appendChild(wrapper.firstElementChild);
    calculateLiveBudget();
  });
  document.addEventListener('click', function(e){
    const btn=e.target.closest('[data-remove-item]'); if(!btn) return;
    btn.closest('.repeater-item,.nested-line')?.remove(); calculateLiveBudget();
  });
  document.addEventListener('change', function(e){
    const card=e.target.closest('.type-card'); if(card && e.target.matches('input[type="checkbox"]')){
      card.classList.toggle('selected', e.target.checked);
      const section=document.querySelector(card.dataset.sectionTarget); if(section) section.style.display=e.target.checked?'block':'none';
    }
    if(e.target.matches('[data-budget]')) calculateLiveBudget();
  });
  document.addEventListener('input', function(e){ if(e.target.matches('[data-budget]')) calculateLiveBudget(); });
  function calculateLiveBudget(){
    let total=0;
    document.querySelectorAll('[data-budget]').forEach(inp=>{ const v=parseFloat((inp.value||'').replace(/,/g,'')); if(!isNaN(v)) total+=v; });
    document.querySelectorAll('[data-budget-total]').forEach(el=>el.textContent=total.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})+' EGP');
  }
  window.calculateLiveBudget = calculateLiveBudget;
  document.addEventListener('DOMContentLoaded', calculateLiveBudget);
  document.addEventListener('DOMContentLoaded', function(){
    document.querySelectorAll('[data-swal-message]').forEach(el=>crmToast(el.dataset.swalMessage, el.dataset.swalIcon || 'success'));
    const sidebar=document.querySelector('.sidebar');
    document.querySelectorAll('[data-mobile-menu]').forEach(btn=>btn.addEventListener('click',()=>sidebar?.classList.toggle('open')));
  });
})();

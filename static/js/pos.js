document.addEventListener('DOMContentLoaded', () => {
    const sellButtons = document.querySelectorAll('.btn-sell');
    const loadingOverlay = document.getElementById('loading-overlay');
    const toastContainer = document.getElementById('toast-container');

    sellButtons.forEach(button => {
        button.addEventListener('click', async (e) => {
            const card = e.target.closest('.product-card');
            const productId = card.dataset.id;
            const productName = card.dataset.name;
            
            // Mostrar indicador visual asíncrono
            showLoading(true);

            try {
                const response = await fetch('/api/venta', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        producto_id: productId,
                        cantidad: 1
                    })
                });

                if (!response.ok) throw new Error('Error en la red');
                
                const data = await response.json();
                
                // Mostrar éxito
                showToast(`¡Venta de ${productName} registrada!`);
            } catch (error) {
                console.error('Error al registrar venta:', error);
                showToast(`Error al vender ${productName}`, true);
            } finally {
                showLoading(false);
            }
        });
    });

    function showLoading(show) {
        if (show) {
            loadingOverlay.classList.remove('hidden');
        } else {
            loadingOverlay.classList.add('hidden');
        }
    }

    function showToast(message, isError = false) {
        const toast = document.createElement('div');
        toast.className = 'toast';
        if (isError) toast.style.backgroundColor = 'var(--danger)';
        toast.textContent = message;
        
        toastContainer.appendChild(toast);
        
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(100%)';
            toast.style.transition = 'all 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }
});

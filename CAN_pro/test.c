#include "stm32f4xx.h"

#define UART1_BUF_SIZE 260

volatile uint8_t uart1_rx_buf[UART1_BUF_SIZE];
volatile uint16_t uart1_rx_idx = 0;
volatile uint16_t uart1_frame_len = 0;
volatile uint8_t uart1_receiving = 0;
volatile uint8_t uart1_frame_ready = 0;

void delay_ms(uint32_t ms);
void USART2_Init(void);
void USART2_SendChar(char c);
void USART2_SendString(const char *str);
void USART1_Init(void);

void USART1_IRQHandler(void) {
    if (USART1->SR & USART_SR_RXNE) {
        uint8_t data = USART1->DR;

        if (!uart1_receiving) {
            uart1_rx_idx = 0;
            uart1_frame_len = 0;
            uart1_receiving = 1;
        }

        uart1_rx_buf[uart1_rx_idx++] = data;

        if (uart1_rx_idx == 1) {
            // Đã nhận model, chưa biết frame length
        } else if (uart1_rx_idx == 2) {
            // Đã nhận model + 1 byte id, chờ thêm để xác định id đủ chưa
        } else if (uart1_rx_idx == 3) {
            // Đã nhận model + 2 byte id (Standard)
            if (uart1_rx_buf[0] == 0) {
                // Standard: model(1) + id(2) + length(1)
                uart1_frame_len = 1 + 2 + 1;
            }
        } else if (uart1_rx_idx == 5) {
            // Đã nhận model + 4 byte id (Extended)
            if (uart1_rx_buf[0] == 1) {
                // Extended: model(1) + id(4) + length(1)
                uart1_frame_len = 1 + 4 + 1;
            }
        }

        // Khi đã nhận xong length byte, xác định tổng frame length
        if ((uart1_rx_buf[0] == 0 && uart1_rx_idx == 4) || (uart1_rx_buf[0] == 1 && uart1_rx_idx == 6)) {
            uint8_t data_len = uart1_rx_buf[uart1_rx_idx - 1];
            if (uart1_rx_buf[0] == 0) {
                uart1_frame_len = 1 + 2 + 1 + data_len;
            } else {
                uart1_frame_len = 1 + 4 + 1 + data_len;
            }
        }

        // Khi nhận đủ frame
        if (uart1_frame_len && uart1_rx_idx == uart1_frame_len) {
            uart1_frame_ready = 1;
            uart1_receiving = 0;
        }
        // Nếu quá dài, reset
        if (uart1_rx_idx >= UART1_BUF_SIZE) {
            uart1_rx_idx = 0;
            uart1_receiving = 0;
        }
    }
}

void USART1_Init(void) {
    RCC->AHB1ENR |= RCC_AHB1ENR_GPIOAEN;
    RCC->APB2ENR |= RCC_APB2ENR_USART1EN;

    // PA9 (TX), PA10 (RX) AF7
    GPIOA->MODER &= ~((3 << (9*2)) | (3 << (10*2)));
    GPIOA->MODER |=  (2 << (9*2)) | (2 << (10*2));
    GPIOA->AFR[1] &= ~((0xF << ((9-8)*4)) | (0xF << ((10-8)*4)));
    GPIOA->AFR[1] |= (7 << ((9-8)*4)) | (7 << ((10-8)*4));

    USART1->BRR = 16000000/115200; // 16MHz clock
    USART1->CR1 = USART_CR1_RE | USART_CR1_RXNEIE | USART_CR1_UE;

    NVIC_EnableIRQ(USART1_IRQn);
}

void USART2_Init(void) {
    RCC->AHB1ENR |= RCC_AHB1ENR_GPIOAEN;
    RCC->APB1ENR |= RCC_APB1ENR_USART2EN;

    GPIOA->MODER &= ~(3 << (2 * 2));
    GPIOA->MODER |=  (2 << (2 * 2));
    GPIOA->AFR[0]  |= (7 << (4 * 2));

    USART2->BRR = (8 << 4) | 11; // 16MHz/115200
    USART2->CR1 = USART_CR1_TE | USART_CR1_UE;
}

void USART2_SendChar(char c) {
    while (!(USART2->SR & USART_SR_TXE));
    USART2->DR = c;
}

void USART2_SendString(const char *str) {
    while (*str) {
        USART2_SendChar(*str++);
    }
}

void delay_ms(uint32_t ms) {
    for (uint32_t i = 0; i < ms * 8000; i++) {
        __NOP();
    }
}

int main(void) {
    USART1_Init();
    USART2_Init();

    while (1) {
        if (uart1_frame_ready) {
            // Gửi toàn bộ frame sang USART2
            for (uint16_t i = 0; i < uart1_frame_len; i++) {
                USART2_SendChar(uart1_rx_buf[i]);
            }
            uart1_frame_ready = 0;
            uart1_rx_idx = 0;
        }
    }
}

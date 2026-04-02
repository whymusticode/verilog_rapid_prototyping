library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use IEEE.NUMERIC_STD.ALL;

entity frame_buffer is
    Port ( clka  : in  STD_LOGIC;
           wea   : in  STD_LOGIC_VECTOR(0 downto 0);
           addra : in  STD_LOGIC_VECTOR(16 downto 0);
           dina  : in  STD_LOGIC_VECTOR(11 downto 0);
           clkb  : in  STD_LOGIC;
           addrb : in  STD_LOGIC_VECTOR(16 downto 0);
           doutb : out STD_LOGIC_VECTOR(11 downto 0));
end frame_buffer;

architecture Behavioral of frame_buffer is
    type ram_type is array(0 to 131071) of std_logic_vector(11 downto 0);
    shared variable ram : ram_type := (others => (others => '0'));
begin

    process(clka)
    begin
        if rising_edge(clka) then
            if wea(0) = '1' then
                ram(to_integer(unsigned(addra))) := dina;
            end if;
        end if;
    end process;

    process(clkb)
    begin
        if rising_edge(clkb) then
            doutb <= ram(to_integer(unsigned(addrb)));
        end if;
    end process;

end Behavioral;
